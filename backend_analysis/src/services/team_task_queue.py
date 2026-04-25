# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional

from src.services.team_service import build_default_workflow, run_team_with_progress

if TYPE_CHECKING:
    from asyncio import Queue as AsyncQueue
    from api.v1.schemas.team import TeamRunRequest

logger = logging.getLogger(__name__)


class TeamTaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TeamTaskInfo:
    task_id: str
    stock_code: str
    trade_date: str
    llm_provider: str
    status: TeamTaskStatus = TeamTaskStatus.PENDING
    progress: int = 0
    message: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    current_step: Optional[str] = None
    workflow: List[Dict[str, Any]] = field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "stock_code": self.stock_code,
            "trade_date": self.trade_date,
            "llm_provider": self.llm_provider,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "current_step": self.current_step,
            "workflow": self.workflow,
            "result": self.result,
            "error": self.error,
        }

    def copy(self) -> "TeamTaskInfo":
        return TeamTaskInfo(
            task_id=self.task_id,
            stock_code=self.stock_code,
            trade_date=self.trade_date,
            llm_provider=self.llm_provider,
            status=self.status,
            progress=self.progress,
            message=self.message,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
            current_step=self.current_step,
            workflow=[dict(item) for item in self.workflow],
            result=self.result,
            error=self.error,
        )


class TeamTaskQueue:
    _instance: Optional["TeamTaskQueue"] = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, max_workers: int = 2):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._max_workers = max_workers
        self._executor: Optional[ThreadPoolExecutor] = None
        self._tasks: Dict[str, TeamTaskInfo] = {}
        self._futures: Dict[str, Future] = {}
        self._subscribers: List["AsyncQueue"] = []
        self._subscribers_lock = threading.Lock()
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        self._data_lock = threading.RLock()
        self._initialized = True

    @property
    def executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=self._max_workers, thread_name_prefix="team_task_")
        return self._executor

    def submit_task(self, request: "TeamRunRequest") -> TeamTaskInfo:
        workflow = build_default_workflow(request.roles)
        task = TeamTaskInfo(
            task_id=uuid.uuid4().hex,
            stock_code=request.stock_code.upper(),
            trade_date=request.trade_date,
            llm_provider=request.llm_provider,
            message="Team task accepted",
            workflow=[step.model_dump() for step in workflow],
        )
        with self._data_lock:
            self._tasks[task.task_id] = task
            self._futures[task.task_id] = self.executor.submit(self._execute_task, task.task_id, request)
        self._broadcast_event("team_task_created", task.to_dict())
        return task

    def get_task(self, task_id: str) -> Optional[TeamTaskInfo]:
        with self._data_lock:
            task = self._tasks.get(task_id)
            return task.copy() if task else None

    def list_pending_tasks(self) -> List[TeamTaskInfo]:
        with self._data_lock:
            return [task.copy() for task in self._tasks.values() if task.status in (TeamTaskStatus.PENDING, TeamTaskStatus.PROCESSING)]

    def list_all_tasks(self, limit: int = 50) -> List[TeamTaskInfo]:
        with self._data_lock:
            tasks = sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)
            return [task.copy() for task in tasks[:limit]]

    def get_task_stats(self) -> Dict[str, int]:
        with self._data_lock:
            return {
                "total": len(self._tasks),
                "pending": sum(1 for t in self._tasks.values() if t.status == TeamTaskStatus.PENDING),
                "processing": sum(1 for t in self._tasks.values() if t.status == TeamTaskStatus.PROCESSING),
            }

    def _execute_task(self, task_id: str, request: "TeamRunRequest") -> None:
        with self._data_lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            task.status = TeamTaskStatus.PROCESSING
            task.progress = 5
            task.message = "Starting team workflow..."
            task.started_at = datetime.now()
        self._broadcast_event("team_task_started", task.to_dict())

        def progress_callback(payload: Dict[str, Any]) -> None:
            with self._data_lock:
                current = self._tasks.get(task_id)
                if not current:
                    return
                current.current_step = payload.get("current_step") or current.current_step
                current.progress = int(payload.get("progress", current.progress))
                current.message = str(payload.get("message", current.message or ""))
                workflow = payload.get("workflow")
                if isinstance(workflow, list):
                    current.workflow = workflow
                snapshot = current.copy()
            self._broadcast_event("team_task_updated", snapshot.to_dict())

        try:
            result = run_team_with_progress(request, progress_callback)
            with self._data_lock:
                current = self._tasks.get(task_id)
                if not current:
                    return
                current.status = TeamTaskStatus.COMPLETED
                current.progress = 100
                current.message = "Team workflow completed"
                current.completed_at = datetime.now()
                current.result = result.model_dump()
            self._broadcast_event("team_task_completed", current.to_dict())
        except Exception as exc:
            with self._data_lock:
                current = self._tasks.get(task_id)
                if not current:
                    return
                current.status = TeamTaskStatus.FAILED
                current.completed_at = datetime.now()
                current.error = str(exc)
                current.message = "Team workflow failed"
            self._broadcast_event("team_task_failed", current.to_dict())

    def subscribe(self, queue: "AsyncQueue") -> None:
        with self._subscribers_lock:
            self._subscribers.append(queue)
            try:
                self._main_loop = asyncio.get_running_loop()
            except RuntimeError:
                try:
                    self._main_loop = asyncio.get_event_loop()
                except RuntimeError:
                    pass

    def unsubscribe(self, queue: "AsyncQueue") -> None:
        with self._subscribers_lock:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    def _broadcast_event(self, event_type: str, data: Dict[str, Any]) -> None:
        with self._subscribers_lock:
            subscribers = self._subscribers.copy()
            loop = self._main_loop
        if not subscribers or loop is None:
            return
        event = {"type": event_type, "data": data}
        for queue in subscribers:
            loop.call_soon_threadsafe(queue.put_nowait, event)


def get_team_task_queue() -> TeamTaskQueue:
    return TeamTaskQueue()
