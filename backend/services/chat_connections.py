"""In-memory WebSocket connection registry + fan-out.

This module is the SINGLE in-memory component that multi-worker scaling will
touch: when web:N arrives, fanout() will additionally redis.publish() to a
federation channel that other workers subscribe to. The local CONNECTIONS map
stays per-worker (it holds live WebSocket objects, not serializable data).

Per spec section 'Точка расширения на multi-worker': CONNECTIONS is the only
known single-worker gap; the per-user rate limiter is already on Redis.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Callable

from starlette.websockets import WebSocket

logger = logging.getLogger("HHB_B2B")

# user_id -> set of open WebSockets (one user may have multiple tabs)
CONNECTIONS: dict[int, set[WebSocket]] = defaultdict(set)


def add_connection(user_id: int, ws: WebSocket) -> None:
    CONNECTIONS[user_id].add(ws)


def remove_connection(user_id: int, ws: WebSocket) -> None:
    conns = CONNECTIONS.get(user_id)
    if conns:
        conns.discard(ws)
        if not conns:
            del CONNECTIONS[user_id]


async def fanout(
    channel_id: int,
    payload: dict,
    members: Callable[[int], list[int]],
    exclude_user: int | None = None,
) -> None:
    """Push `payload` to every online member of `channel_id`.

    `members(channel_id) -> [user_id, ...]` is injected by the caller (the
    message-send path) so this module stays free of DB imports and trivially
    testable. Online = has at least one entry in CONNECTIONS.

    Dead sockets raise on send_json; we swallow and let the heartbeat cycle
    (chat_ws.py) reap them.
    """
    for user_id in members(channel_id):
        if user_id == exclude_user:
            continue
        for ws in list(CONNECTIONS.get(user_id, ())):
            try:
                await ws.send_json(payload)
            except Exception:
                # socket is gone/stale; heartbeat will clean CONNECTIONS
                pass
