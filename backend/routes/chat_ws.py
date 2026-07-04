"""WebSocket handler for chat: /ws/chat?ticket=<single-use-ticket>.

Auth flow: client first POST /api/chat/ws-ticket (Bearer) to get a 30s ticket,
then opens the WS with ?ticket=. GETDEL atomically consumes the ticket (no race).
The handler registers the socket in CONNECTIONS so fanout() can push to it,
and reads incoming frames (typing indicators). Heartbeat: handled by uvicorn
default ping/pong; dead sockets are reaped when send_json fails.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.chat_connections import add_connection, remove_connection
from services.chat_redis import consume_ws_ticket

logger = logging.getLogger("HHB_B2B")

router = APIRouter()


@router.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket):
    # Accept must come before reading query params in some versions; read first.
    ticket = websocket.query_params.get("ticket")
    if not ticket:
        await websocket.accept()  # must accept before close in starlette
        await websocket.close(code=4401)
        return
    user_id_str = consume_ws_ticket(ticket)
    if not user_id_str:
        await websocket.accept()
        await websocket.close(code=4401)
        return

    user_id = int(user_id_str)
    await websocket.accept()
    add_connection(user_id, websocket)
    logger.info(f"[chat-ws] user {user_id} connected")

    try:
        while True:
            # We mostly push; incoming frames are typing indicators.
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type == "typing":
                channel_id = data.get("channel_id")
                # fan out typing to other members of the channel
                from services.chat_connections import fanout
                from services.chat_service import _members_of
                members = await _members_of(channel_id)
                await fanout(
                    channel_id=channel_id,
                    payload={"type": "typing", "channel_id": channel_id, "user_id": user_id},
                    members=lambda _c: members,
                    exclude_user=user_id,
                )
    except WebSocketDisconnect:
        logger.info(f"[chat-ws] user {user_id} disconnected")
    except Exception as e:
        logger.warning(f"[chat-ws] user {user_id} error: {e}")
    finally:
        remove_connection(user_id, websocket)
