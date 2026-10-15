"""Structured nightly pipeline orchestrator.

This replaces the brittle shell-only flow with a Python runner that:
- updates automation status in one place
- polls Anthropic batch status via structured APIs instead of grepping logs
- keeps training/cache steps conditional on fresh OHLC coverage
- records step details for the UI
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.automation.status import fail_run, finish_run, start_run, update_run
from backend.batch_collect import check_status, collect_results
from backend.database import get_conn


ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "logs"


class PipelineError(RuntimeError):
    pass


@dataclass
class Config:
    root: Path
    database_path: str
    main_python: str
    finbert_python: str
    min_ohlc_coverage: int
    batch_max_retries: int
    batch_retry_interval: int
    recent_fetch_days: int


def _load_config() -> Config:
    main_python = os.environ.get("MAIN_PYTHON") or "/Users/ivy_ai/OpenBB/conda/envs/openbb/bin/python"
    finbert_python = os.environ.get("FINBERT_PYTHON") or "/usr/bin/python3"
    return Config(
        root=ROOT,
        database_path=os.environ.get("DATABASE_PATH", str(ROOT / "pokieticker.db")),
        main_python=main_python,
        finbert_python=finbert_python,
        min_ohlc_coverage=int(os.environ.get("MIN_OHLC_COVERAGE", "100")),
        batch_max_retries=int(os.environ.get("BATCH_MAX_RETRIES", "18")),
        batch_retry_interval=int(os.environ.get("BATCH_RETRY_INTERVAL", "1200")),
        recent_fetch_days=int(os.environ.get("RECENT_FETCH_DAYS", "2")),
    )


def _env(config: Config) -> dict[str, str]:
    env = os.environ.copy()
    env["DATABASE_PATH"] = config.database_path
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _log_line(log_file: Path, text: str) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")


def _run_cmd(config: Config, log_file: Path, cmd: list[str], *, allow_failure: bool = False) -> subprocess.CompletedProcess[str]:
    _log_line(log_file, f"$ {' '.join(cmd)}")
    proc = subprocess.run(
        cmd,
        cwd=str(config.root),
        env=_env(config),
        text=True,
        capture_output=True,
    )
    if proc.stdout:
        _log_line(log_file, proc.stdout)
    if proc.stderr:
        _log_line(log_file, proc.stderr)
    if proc.returncode != 0 and not allow_failure:
        raise PipelineError(f"Command failed ({proc.returncode}): {' '.join(cmd)}")
    return proc


def _collect_ohlc_coverage() -> dict[str, Any]:
    conn = get_conn()
    target = conn.execute("SELECT MAX(date) AS max_date FROM ohlc").fetchone()["max_date"]
    tracked = conn.execute("SELECT COUNT(*) AS c FROM tickers").fetchone()["c"]
    covered = conn.execute(
        "SELECT COUNT(DISTINCT symbol) AS c FROM ohlc WHERE date = ?",
        (target,),
    ).fetchone()["c"]
    conn.close()
    return {
        "target_date": target,
        "tracked": int(tracked or 0),
        "covered": int(covered or 0),
    }


def _latest_uncollected_batch_id() -> str | None:
    conn = get_conn()
    row = conn.execute(
        """
        SELECT batch_id
        FROM batch_jobs
        WHERE status NOT IN ('collected', 'expired')
        ORDER BY created_at DESC
        LIMIT 1
        """
    ).fetchone()
    conn.close()
    return row["batch_id"] if row else None


def _run_recent_finbert(config: Config, log_file: Path) -> None:
    _run_cmd(
        config,
        log_file,
        [config.finbert_python, "-m", "backend.finbert_reclassify_recent", "--days", "4"],
        allow_failure=True,
    )


def _run_rag_rebuild(config: Config, log_file: Path) -> None:
    cmd = [
        str(config.root / "backend_analysis" / "venv" / "bin" / "python3"),
        "build_rag.py",
        "--collection",
        "news",
        "--days-back",
        "3",
        "--force",
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(config.root / "backend_analysis"),
        env=_env(config),
        text=True,
        capture_output=True,
    )
    if proc.stdout:
        _log_line(log_file, proc.stdout)
    if proc.stderr:
        _log_line(log_file, proc.stderr)


def run_nightly() -> int:
    config = _load_config()
    log_file = LOG_DIR / f"nightly_{time.strftime('%Y%m%d')}.log"
    _log_line(log_file, f"=== {time.strftime('%Y-%m-%d %H:%M:%S')} ===")

    run_id = start_run("nightly_pipeline", step="start", message="Nightly pipeline started")
    try:
        update_run(run_id, step="fetch_recent", message="Fetching latest OHLC and news")
        _run_cmd(
            config,
            log_file,
            [config.main_python, "-m", "backend.update_recent", "--days", str(config.recent_fetch_days)],
        )

        update_run(run_id, step="ensure_ohlc", message="Verifying OHLC coverage")
        _run_cmd(config, log_file, [config.main_python, "-m", "backend.ensure_recent_ohlc"])
        coverage = _collect_ohlc_coverage()
        coverage["threshold"] = config.min_ohlc_coverage
        update_run(
            run_id,
            step="ensure_ohlc",
            message=f"OHLC coverage {coverage['covered']}/{coverage['tracked']} for {coverage['target_date']}",
            details=coverage,
        )
        skip_training = coverage["covered"] < config.min_ohlc_coverage

        update_run(run_id, step="submit_batch", message="Submitting Anthropic batch")
        _run_cmd(config, log_file, [config.main_python, "-m", "backend.batch_submit"])
        batch_id = _latest_uncollected_batch_id()
        update_run(run_id, step="submit_batch", message="Anthropic batch submitted", details={"batch_id": batch_id})

        update_run(run_id, step="wait_batch", message="Waiting for batch completion")
        if not batch_id:
            update_run(run_id, step="wait_batch", message="No pending batch found — skipping wait")
        else:
            batch_collected = False
            for attempt in range(1, config.batch_max_retries + 1):
                status = check_status(batch_id)
                batch_status = status["status"]
                update_run(
                    run_id,
                    step="wait_batch",
                    message=f"Batch {batch_id} status: {batch_status} (attempt {attempt}/{config.batch_max_retries})",
                    details={"batch_id": batch_id, "batch_status": status, "batch_attempt": attempt},
                )

                if batch_status == "ended":
                    stats = collect_results(batch_id)
                    update_run(
                        run_id,
                        step="collect_batch",
                        message="Collected batch results; running FinBERT",
                        details={"batch_id": batch_id, "collect_stats": stats},
                    )
                    batch_collected = True
                    break

                if batch_status in ("canceled", "canceling", "expired"):
                    _log_line(log_file, f"Batch {batch_id} is {batch_status} — skipping collection, continuing pipeline")
                    update_run(
                        run_id,
                        step="wait_batch",
                        message=f"Batch {batch_id} {batch_status} — skipping, continuing pipeline",
                        details={"batch_id": batch_id, "batch_status": status},
                    )
                    break

                if attempt < config.batch_max_retries:
                    time.sleep(config.batch_retry_interval)
                else:
                    # Retry limit reached — log and continue instead of failing the whole pipeline
                    _log_line(log_file, f"Batch {batch_id} not collected after {config.batch_max_retries} retries — continuing without batch results")
                    update_run(
                        run_id,
                        step="wait_batch",
                        message=f"Batch retry limit reached — continuing pipeline without batch results",
                        details={"batch_id": batch_id, "attempts": config.batch_max_retries},
                    )

        update_run(run_id, step="finbert", message="Re-running recent FinBERT")
        _run_recent_finbert(config, log_file)

        if not skip_training:
            update_run(run_id, step="train_detail", message="Training detail models")
            _run_cmd(config, log_file, [config.main_python, "-m", "backend.ml.train"])

            update_run(run_id, step="cache_detail_forecast", message="Caching detail forecasts")
            _run_cmd(config, log_file, [config.main_python, "-m", "backend.ml.daily_forecast"])
        else:
            update_run(
                run_id,
                step="train_detail",
                message="Skipped model training because OHLC coverage threshold was not met",
                details={"skip_training": True},
            )

        update_run(run_id, step="update_rag", message="Rebuilding RAG index")
        _run_rag_rebuild(config, log_file)

        finish_run(
            run_id,
            message="Nightly pipeline completed",
            details={
                "target_date": coverage["target_date"],
                "tracked": coverage["tracked"],
                "covered": coverage["covered"],
                "threshold": coverage["threshold"],
                "skip_training": skip_training,
            },
        )
        _log_line(log_file, f"=== Done {time.strftime('%Y-%m-%d %H:%M:%S')} — forecasts ready for next trading day ===")
        return 0
    except Exception as exc:
        fail_run(run_id, f"nightly_pipeline failed: {type(exc).__name__}: {exc}")
        _log_line(log_file, f"=== Failed: {type(exc).__name__}: {exc} ===")
        return 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    raise SystemExit(run_nightly())


if __name__ == "__main__":
    main()
