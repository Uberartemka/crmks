"""REST endpoints for chat: channels, messages, members, read-state, ws-ticket.

All endpoints require a staff role (admin/manager/employee); clients get 403.
Pattern matches defects/orders routers: thin route → service call.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, Request

from auth_deps import get_current_user as _get_current_user
from schemas.chat import ChannelCreate, MessageCreate, MessageUpdate, MemberAdd
from services.chat_service import (
    list_channels,
    create_topic_channel,
    list_messages,
    send_message,
    edit_message,
    delete_message,
    mark_read,
    unread_counts,
    add_member,
    remove_member,
)
from services.chat_redis import issue_ws_ticket

router = APIRouter(tags=["chat"])


def get_current_user():
    async def _dep(request: Request):
        return _get_current_user(request)
    return _dep


@router.get("/api/chat/channels")
async def channels_endpoint(current_user: Dict[str, Any] = Depends(get_current_user())):
    return await list_channels(current_user=current_user)


@router.post("/api/chat/channels")
async def create_channel_endpoint(
    data: ChannelCreate,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await create_topic_channel(data=data, current_user=current_user)


@router.get("/api/chat/channels/{channel_id}/messages")
async def messages_endpoint(
    channel_id: int,
    before: Optional[int] = Query(None),
    limit: int = Query(50, le=100),
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await list_messages(channel_id=channel_id, current_user=current_user, before=before, limit=limit)


@router.post("/api/chat/channels/{channel_id}/messages")
async def send_message_endpoint(
    channel_id: int,
    data: MessageCreate,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    msg = await send_message(channel_id=channel_id, data=data, current_user=current_user)
    # fan out to online members (best-effort push; history is the source of truth)
    from services.chat_connections import fanout
    from services.chat_service import _members_of
    members = await _members_of(channel_id)
    await fanout(
        channel_id=channel_id,
        payload={"type": "message", "channel_id": channel_id, "message": msg},
        members=lambda _c: members,
        exclude_user=current_user["id"],
    )
    # bump unread for everyone else
    await fanout(
        channel_id=channel_id,
        payload={"type": "unread", "channel_id": channel_id},
        members=lambda _c: members,
        exclude_user=current_user["id"],
    )
    return msg


@router.patch("/api/chat/messages/{message_id}")
async def edit_message_endpoint(
    message_id: int,
    data: MessageUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await edit_message(message_id=message_id, data=data, current_user=current_user)


@router.delete("/api/chat/messages/{message_id}")
async def delete_message_endpoint(
    message_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await delete_message(message_id=message_id, current_user=current_user)


@router.post("/api/chat/channels/{channel_id}/read")
async def read_endpoint(
    channel_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    """Mark a channel read up to its latest message. Bound to channel (not a
    single message) — simpler and more robust than tracking per-message reads."""
    from db import get_db, q
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(q("SELECT MAX(id) FROM messages WHERE channel_id = %s"), (channel_id,))
        last = cur.fetchone()[0] or 0
    finally:
        conn.close()
    return await mark_read(channel_id=channel_id, last_read_message_id=last, current_user=current_user)


@router.get("/api/chat/unread")
async def unread_endpoint(current_user: Dict[str, Any] = Depends(get_current_user())):
    return await unread_counts(current_user=current_user)


@router.post("/api/chat/channels/{channel_id}/members")
async def add_member_endpoint(
    channel_id: int,
    data: MemberAdd,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await add_member(channel_id=channel_id, user_id=data.user_id, current_user=current_user)


@router.delete("/api/chat/channels/{channel_id}/members/{user_id}")
async def remove_member_endpoint(
    channel_id: int,
    user_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await remove_member(channel_id=channel_id, user_id=user_id, current_user=current_user)


@router.post("/api/chat/ws-ticket")
async def ws_ticket_endpoint(current_user: Dict[str, Any] = Depends(get_current_user())):
    from schemas.chat import WsTicketOut
    if current_user["role"] not in ("admin", "manager", "employee"):
        from fastapi import HTTPException
        raise HTTPException(403, "Чат доступен только сотрудникам")
    return WsTicketOut(ticket=issue_ws_ticket(current_user["id"]))
