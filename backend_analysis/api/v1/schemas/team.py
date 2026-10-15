# -*- coding: utf-8 -*-
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


TeamRole = Literal["market", "social", "news", "fundamentals", "ivy"]
TeamProvider = Literal["anthropic", "google"]
TeamStepStatus = Literal["selected", "active", "completed", "skipped", "failed"]


class TeamRunRequest(BaseModel):
    stock_code: str = Field(..., description="股票代码")
    trade_date: str = Field(..., description="交易日期 YYYY-MM-DD")
    llm_provider: TeamProvider = Field("anthropic", description="LLM 提供方")
    deep_model: Optional[str] = Field(None, description="深度模型")
    quick_model: Optional[str] = Field(None, description="快速模型")
    roles: List[TeamRole] = Field(default_factory=lambda: ["market", "social", "news", "fundamentals", "ivy"])
    max_debate_rounds: int = Field(1, ge=1, le=3)
    max_risk_discuss_rounds: int = Field(1, ge=1, le=3)


class TeamWorkflowStep(BaseModel):
    key: str
    label: str
    icon: str
    status: TeamStepStatus


class TeamRunResponse(BaseModel):
    run_id: str
    stock_code: str
    trade_date: str
    llm_provider: TeamProvider
    deep_model: str
    quick_model: str
    roles: List[TeamRole]
    workflow: List[TeamWorkflowStep]
    reports: Dict[str, str]
    final_decision: str
    investment_plan: Optional[str] = None
    markdown_report: str
    state: Dict[str, Any]


class TeamTaskAccepted(BaseModel):
    task_id: str = Field(..., description="任务 ID")
    status: Literal["pending", "processing"] = Field(..., description="任务状态")
    message: Optional[str] = Field(None, description="提示信息")


class TeamTaskInfo(BaseModel):
    task_id: str
    stock_code: str
    trade_date: str
    llm_provider: TeamProvider
    status: Literal["pending", "processing", "completed", "failed"]
    progress: int = Field(0, ge=0, le=100)
    message: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    current_step: Optional[str] = None
    workflow: List[TeamWorkflowStep] = Field(default_factory=list)
    result: Optional[TeamRunResponse] = None
    error: Optional[str] = None


class TeamTaskListResponse(BaseModel):
    total: int
    pending: int
    processing: int
    tasks: List[TeamTaskInfo]
