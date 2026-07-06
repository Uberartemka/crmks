from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ChannelCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    type: str = Field("topic", pattern="^(topic)$")  # general/department создаются сидом/админкой отдельно
    member_ids: list[int] = Field(default_factory=list)  # для topic: кого добавить сразу


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)
    reply_to_id: Optional[int] = None
    attachment_id: Optional[int] = None


class MessageUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)


class MemberAdd(BaseModel):
    user_id: int


class WsTicketOut(BaseModel):
    ticket: str
    expires_in: int = 30
