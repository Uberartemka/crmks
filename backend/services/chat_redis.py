"""Chat Redis helpers: ws-ticket (atomic GETDEL) + per-user message rate limit.

Reuses the existing Redis client from pdf_service (lazy singleton, decode_responses=True).
No new Redis pool is created.
"""
from __future__ import annotations

import secrets
import time

# reuse the existing lazy client — do NOT create a second pool
from services.pdf_service import _get_redis

_TICKET_PREFIX = "chat:ws-ticket:"
_TICKET_TTL = 30           # seconds
_RATE_PREFIX = "chat:rl:"
_RATE_WINDOW = 60          # 1-minute bucket
_RATE_LIMIT = 20           # max messages per user per minute


def _ticket_key(ticket: str) -> str:
    return f"{_TICKET_PREFIX}{ticket}"


def issue_ws_ticket(user_id: int) -> str:
    """Mint a single-use, 30s ticket bound to user_id."""
    ticket = secrets.token_urlsafe(32)
    _get_redis().setex(_ticket_key(ticket), _TICKET_TTL, str(user_id))
    return ticket


def consume_ws_ticket(ticket: str) -> str | None:
    """Atomically read+delete a ticket. Returns user_id (str) or None if
    missing/expired/already-consumed.

    GETDEL (Redis 6.2+) closes the race window that get+delete would open:
    two concurrent handshakes with the same ticket would both see the user_id
    before either deletes. GETDEL is one atomic command.
    """
    return _get_redis().getdel(_ticket_key(ticket))


def allow_message(user_id: int) -> bool:
    """Per-user, fixed-minute-window limiter via INCR + EXPIRE.

    Correct on 1 worker and N (unlike an in-memory defaultdict): the counter
    lives in Redis, shared across all workers. Fixed window is approximate but
    sufficient for flood protection (a burst at the minute boundary is harmless
    for chat).
    """
    r = _get_redis()
    bucket = int(time.time()) // _RATE_WINDOW
    key = f"{_RATE_PREFIX}{user_id}:{bucket}"
    count = r.incr(key)
    if count == 1:
        r.expire(key, _RATE_WINDOW * 2)   # self-cleanup, TTL > window
    return count <= _RATE_LIMIT
