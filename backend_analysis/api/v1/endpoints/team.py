# -*- coding: utf-8 -*-
import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.team import TeamRunRequest, TeamRunResponse, TeamTaskAccepted, TeamTaskInfo, TeamTaskListResponse
from src.services.team_service import run_team
from src.services.team_task_queue import get_team_task_queue

router = APIRouter()


@router.post(
    "/run",
    response_model=TeamRunResponse,
    responses={
        400: {"description": "请求参数错误", "model": ErrorResponse},
        500: {"description": "运行失败", "model": ErrorResponse},
    },
    summary="运行 Team 多代理分析",
    description="在本地直接调用 TradingAgents + IvyTrader 分析链路，返回可视化页面使用的结果。",
)
def run_team_endpoint(request: TeamRunRequest) -> TeamRunResponse:
    if not request.roles:
        raise HTTPException(
            status_code=400,
            detail={"error": "validation_error", "message": "至少选择一个角色"},
        )

    try:
        return run_team(request)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "team_run_failed", "message": str(exc)},
        ) from exc


@router.post(
    "/run-async",
    response_model=TeamTaskAccepted,
    summary="异步运行 Team 多代理分析",
)
def run_team_async_endpoint(request: TeamRunRequest) -> TeamTaskAccepted:
    task = get_team_task_queue().submit_task(request)
    return TeamTaskAccepted(task_id=task.task_id, status="pending", message="Team task accepted")


@router.get(
    "/tasks",
    response_model=TeamTaskListResponse,
    summary="获取 Team 任务列表",
)
def get_team_tasks(limit: int = 20) -> TeamTaskListResponse:
    queue = get_team_task_queue()
    tasks = [TeamTaskInfo(**task.to_dict()) for task in queue.list_all_tasks(limit=limit)]
    stats = queue.get_task_stats()
    return TeamTaskListResponse(total=stats["total"], pending=stats["pending"], processing=stats["processing"], tasks=tasks)


@router.get(
    "/status/{task_id}",
    response_model=TeamTaskInfo,
    summary="查询 Team 任务状态",
)
def get_team_status(task_id: str) -> TeamTaskInfo:
    task = get_team_task_queue().get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Team task {task_id} not found"})
    return TeamTaskInfo(**task.to_dict())


@router.get(
    "/tasks/stream",
    summary="Team 任务状态 SSE 流",
)
async def team_task_stream():
    async def event_generator():
        queue = get_team_task_queue()
        event_queue: asyncio.Queue = asyncio.Queue()
        yield _format_sse_event("connected", {"message": "Connected to team task stream"})
        for task in queue.list_pending_tasks():
            yield _format_sse_event("team_task_created", task.to_dict())
        queue.subscribe(event_queue)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=30)
                    yield _format_sse_event(event["type"], event["data"])
                except asyncio.TimeoutError:
                    yield _format_sse_event("heartbeat", {"timestamp": datetime.now().isoformat()})
        except asyncio.CancelledError:
            pass
        finally:
            queue.unsubscribe(event_queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _format_sse_event(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
