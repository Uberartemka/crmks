from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, model_validator


class CallLogCreate(BaseModel):
    client_id: Optional[int] = None
    lead_id: Optional[int] = None
    client_name: str
    from_number: Optional[str] = None
    to_number: Optional[str] = None
    direction: Optional[str] = "outgoing"
    call_date: str
    status: str = "scheduled"
    duration: Optional[int] = 0
    recording_url: Optional[str] = None
    notes: str = ""
    is_new_registration: bool = False
    bitrix_call_id: Optional[str] = None


class CallLogOut(BaseModel):
    id: int
    user_id: int
    client_id: Optional[int]
    lead_id: Optional[int]
    client_name: str
    from_number: Optional[str]
    to_number: Optional[str]
    direction: Optional[str]
    call_date: str
    status: str
    duration: Optional[int]
    recording_url: Optional[str]
    notes: str
    is_new_registration: bool
    bitrix_call_id: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]


class NoteCreate(BaseModel):
    title: str
    content: str
    color: Optional[str] = "yellow"
    pinned: bool = False
    tags: List[str] = []
    client_id: Optional[int] = None


class NoteOut(BaseModel):
    id: int
    title: str
    content: str
    color: Optional[str]
    pinned: bool
    tags: List[str]
    client_id: Optional[int]
    created_at: str
    updated_at: str


TaskStatus = Literal["todo", "in_progress", "done", "blocked"]
TaskPriority = Literal["low", "medium", "high", "urgent"]


class TaskCreateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[str] = None
    assignee_id: Optional[int] = None
    client_id: Optional[int] = None
    call_id: Optional[int] = None

    class Config:
        extra = "forbid"


class TaskUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[str] = None
    assignee_id: Optional[int] = None
    client_id: Optional[int] = None

    class Config:
        extra = "forbid"

    @model_validator(mode="after")
    def validate_not_empty(self) -> "TaskUpdateRequest":
        fields = (
            self.title,
            self.description,
            self.status,
            self.priority,
            self.due_date,
            self.assignee_id,
            self.client_id,
        )
        if all(v is None for v in fields):
            raise ValueError("At least one field must be provided")
        return self
