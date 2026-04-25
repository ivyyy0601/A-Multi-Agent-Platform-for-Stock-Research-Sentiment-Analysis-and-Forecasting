"""Automation run status persistence and CLI helpers."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import Any

from backend.database import get_conn, init_db


def _now_iso() -> str:
    return datetime.now().isoformat()


def start_run(pipeline: str, step: str | None = None, message: str | None = None) -> int:
    init_db(verbose=False)
    started_at = _now_iso()
    run_date = started_at[:10]
    conn = get_conn()
    cur = conn.execute(
        """
        INSERT INTO automation_runs (
            pipeline, run_date, status, current_step, message, started_at, details_json
        ) VALUES (?, ?, 'running', ?, ?, ?, ?)
        """,
        (pipeline, run_date, step, message, started_at, json.dumps({})),
    )
    conn.commit()
    run_id = int(cur.lastrowid)
    conn.close()
    return run_id


def update_run(
    run_id: int,
    *,
    step: str | None = None,
    message: str | None = None,
    status: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    init_db(verbose=False)
    conn = get_conn()
    row = conn.execute(
        "SELECT details_json, current_step, message, status FROM automation_runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError(f"automation run {run_id} not found")

    merged_details: dict[str, Any] = {}
    if row["details_json"]:
        try:
            merged_details = json.loads(row["details_json"])
        except Exception:
            merged_details = {}
    if details:
        merged_details.update(details)

    conn.execute(
        """
        UPDATE automation_runs
        SET status = ?,
            current_step = ?,
            message = ?,
            details_json = ?
        WHERE id = ?
        """,
        (
            status or row["status"],
            step if step is not None else row["current_step"],
            message if message is not None else row["message"],
            json.dumps(merged_details, ensure_ascii=True, sort_keys=True),
            run_id,
        ),
    )
    conn.commit()
    conn.close()


def finish_run(run_id: int, message: str | None = None, details: dict[str, Any] | None = None) -> None:
    init_db(verbose=False)
    conn = get_conn()
    row = conn.execute(
        "SELECT details_json, current_step, message FROM automation_runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError(f"automation run {run_id} not found")
    merged_details: dict[str, Any] = {}
    if row["details_json"]:
        try:
            merged_details = json.loads(row["details_json"])
        except Exception:
            merged_details = {}
    if details:
        merged_details.update(details)
    conn.execute(
        """
        UPDATE automation_runs
        SET status = 'completed',
            message = ?,
            finished_at = ?,
            details_json = ?
        WHERE id = ?
        """,
        (
            message if message is not None else row["message"],
            _now_iso(),
            json.dumps(merged_details, ensure_ascii=True, sort_keys=True),
            run_id,
        ),
    )
    conn.commit()
    conn.close()


def fail_run(run_id: int, message: str, details: dict[str, Any] | None = None) -> None:
    init_db(verbose=False)
    conn = get_conn()
    row = conn.execute(
        "SELECT details_json FROM automation_runs WHERE id = ?",
        (run_id,),
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError(f"automation run {run_id} not found")
    merged_details: dict[str, Any] = {}
    if row["details_json"]:
        try:
            merged_details = json.loads(row["details_json"])
        except Exception:
            merged_details = {}
    if details:
        merged_details.update(details)
    conn.execute(
        """
        UPDATE automation_runs
        SET status = 'failed',
            message = ?,
            finished_at = ?,
            details_json = ?
        WHERE id = ?
        """,
        (message, _now_iso(), json.dumps(merged_details, ensure_ascii=True, sort_keys=True), run_id),
    )
    conn.commit()
    conn.close()


def _parse_run(row) -> dict[str, Any]:
    details = {}
    if row["details_json"]:
        try:
            details = json.loads(row["details_json"])
        except Exception:
            details = {}
    return {
        "id": row["id"],
        "pipeline": row["pipeline"],
        "run_date": row["run_date"],
        "status": row["status"],
        "current_step": row["current_step"],
        "message": row["message"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "details": details,
    }


def get_status(limit: int = 20) -> dict[str, Any]:
    init_db(verbose=False)
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT *
        FROM automation_runs
        ORDER BY started_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    runs = [_parse_run(row) for row in rows]

    current_by_pipeline: dict[str, dict[str, Any]] = {}
    latest_by_pipeline: dict[str, dict[str, Any]] = {}
    for run in runs:
        pipeline = run["pipeline"]
        latest_by_pipeline.setdefault(pipeline, run)
        if run["status"] == "running" and pipeline not in current_by_pipeline:
            current_by_pipeline[pipeline] = run

    return {
        "current": current_by_pipeline,
        "latest": latest_by_pipeline,
        "runs": runs,
    }


def _main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start")
    p_start.add_argument("--pipeline", required=True)
    p_start.add_argument("--step")
    p_start.add_argument("--message")

    p_update = sub.add_parser("update")
    p_update.add_argument("--run-id", type=int, required=True)
    p_update.add_argument("--step")
    p_update.add_argument("--message")
    p_update.add_argument("--status")
    p_update.add_argument("--details-json")

    p_finish = sub.add_parser("finish")
    p_finish.add_argument("--run-id", type=int, required=True)
    p_finish.add_argument("--message")
    p_finish.add_argument("--details-json")

    p_fail = sub.add_parser("fail")
    p_fail.add_argument("--run-id", type=int, required=True)
    p_fail.add_argument("--message", required=True)
    p_fail.add_argument("--details-json")

    p_status = sub.add_parser("status")
    p_status.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()

    if args.command == "start":
        print(start_run(args.pipeline, step=args.step, message=args.message))
        return

    details = json.loads(args.details_json) if getattr(args, "details_json", None) else None

    if args.command == "update":
        update_run(args.run_id, step=args.step, message=args.message, status=args.status, details=details)
    elif args.command == "finish":
        finish_run(args.run_id, message=args.message, details=details)
    elif args.command == "fail":
        fail_run(args.run_id, message=args.message, details=details)
    elif args.command == "status":
        print(json.dumps(get_status(limit=args.limit), ensure_ascii=True))


if __name__ == "__main__":
    _main()
