from __future__ import annotations

import os
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.automation.status import get_status
from backend.config import PROJECT_ROOT, settings

router = APIRouter()

PIPELINE_SCRIPTS = {
    "nightly_pipeline": PROJECT_ROOT / "nightly_pipeline.sh",
    "daily_update": PROJECT_ROOT / "daily_update.sh",
    "batch_collect": PROJECT_ROOT / "batch_collect.sh",
}


def _running_run(pipeline: str):
    status = get_status(limit=20)
    return (status.get("current") or {}).get(pipeline)


@router.get("/status")
def automation_status(limit: int = 20):
    return get_status(limit=limit)


@router.post("/run/{pipeline}")
def trigger_automation(pipeline: str):
    if pipeline not in PIPELINE_SCRIPTS:
        raise HTTPException(status_code=404, detail=f"Unknown pipeline: {pipeline}")

    running = _running_run(pipeline)
    if running:
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"{pipeline} is already running",
                "run_id": running["id"],
                "current_step": running.get("current_step"),
            },
        )

    script_path = PIPELINE_SCRIPTS[pipeline]
    if not script_path.exists():
        raise HTTPException(status_code=500, detail=f"Script not found: {script_path}")

    env = os.environ.copy()
    env["DATABASE_PATH"] = settings.database_path
    subprocess.Popen(
        ["/bin/bash", str(script_path)],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {
        "status": "accepted",
        "pipeline": pipeline,
        "message": f"{pipeline} started",
    }
