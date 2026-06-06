from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, Field


class AgentParseLeadsRequest(BaseModel):
    query: str = Field(..., description="Поисковый запрос, например 'подшипники оптом Воронеж'")
    source: str = Field(default="2gis", description="Источник: 2gis, yandex_maps, avito")
    limit: int = Field(default=20, ge=1, le=100)


class ScheduleItem(BaseModel):
    time: str
    type: str  # call/task/kp/followup
    title: str
    lead_id: int | None = None
    task_id: int | None = None
    duration_min: int = 15


class AgentDailyPlanResponse(BaseModel):
    greeting: str
    focus: str
    schedule: list[ScheduleItem]
    calls_target: int
    kp_target: int
    tip: str


class AgentSignal(BaseModel):
    company: str
    signal: str
    urgency: str


class DailyPlanItem(BaseModel):
    user_id: int
    user_name: str
    calls_target: int
    daily_calls: int
    assigned_leads: int
    completed_calls: int
    remaining_calls: int


class TaskInput(BaseModel):
    task_type: str
    payload: Dict[str, Any]
    max_retries: int = 3
