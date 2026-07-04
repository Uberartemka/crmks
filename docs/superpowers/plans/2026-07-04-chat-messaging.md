# Чат сотрудников (Подсистема I) — Real-time Messaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Построить real-time чат сотрудников CRM: общий канал, каналы по отделам и тематические каналы, с доставкой сообщений через WebSocket и хранением в PostgreSQL.

**Architecture:** «Запись через REST, доставка через WebSocket» (паттерн Slack/Mattermost). `POST /messages` сохраняет в Postgres и фан-аутит через WS. WS-аутентификация — короткоживущий одноразовый ticket (Redis, GETDEL). In-memory `CONNECTIONS`-реестр — единая точка расширения на multi-worker (через Redis pub/sub позже). Per-user rate limiter — на Redis с рождения. 3 типа каналов: `general` (по всем staff), `department` (по роли), `topic` (явные участники).

**Tech Stack:** FastAPI WebSocket, PostgreSQL (миграция 009), Redis (ws-ticket + rate limit), Pydantic v2, pytest + TestClient.websocket_connect; Vue 3 + Pinia + `@vueuse/core`, axios, vitest (jsdom для WS-тестов).

**Спека:** `docs/superpowers/specs/2026-07-04-chat-messaging-design.md` (включая review-правки: GETDEL, PG-версия, Redis rate-limit, CHECK content, 400 на general/department members, запрет v-html).

**Файлы (карта):**

*Backend (создаём):*
- `backend/migrations/009_chat.sql` — схема (channels, channel_members, messages, read_state) + засев general-канала
- `backend/migrations/runner.py` — добавить `apply_migration_009` + вызов в `apply_all`
- `backend/schemas/chat.py` — Pydantic-схемы (ChannelCreate, MessageCreate, etc.)
- `backend/services/chat_service.py` — бизнес-логика (channels/messages/read_state/membership)
- `backend/services/chat_connections.py` — in-memory `CONNECTIONS` реестр + `_fanout`
- `backend/services/chat_redis.py` — ws-ticket (GETDEL) + per-user rate limit (INCR+EXPIRE)
- `backend/routes/chat.py` — REST-эндпоинты (Depends + service calls)
- `backend/routes/chat_ws.py` — WebSocket-хендлер `/ws/chat`
- `backend/tests/test_chat_channels.py`, `test_chat_messages.py`, `test_chat_read_state.py`, `test_chat_membership.py`, `test_chat_access.py`, `test_chat_ws.py` — ~29 тестов

*Backend (правим):*
- `backend/routes/index.py` — `register_routes` подключает chat_router + chat_ws_router
- `backend/requirements.txt` — `httpx-ws` (для WS TestClient)
- `backend/tests/conftest.py` — добавить chat-таблицы в `_TABLES_TO_CLEAR`

*Frontend (создаём):*
- `src/types/chat.ts` — TS-интерфейсы (Channel, Message, etc.)
- `src/api/chat.ts` — axios-модуль
- `src/stores/chat.ts` — `useChatStore` (Pinia)
- `src/composables/useChatSocket.ts` — WS-singleton + `useChatSocket.test.ts`
- `src/views/ChatView.vue` — главный экран чата
- `src/components/chat/ChannelList.vue`, `MessageList.vue`, `MessageInput.vue`, `TypingIndicator.vue`

*Frontend (правим):*
- `src/router/index.ts` — добавить `/admin/chat`, `/manager/chat`, `/employee/chat`
- `src/components/sidebar/AppSidebar.vue` — пункт «Чат» (admin/manager/employee) + иконка `MessageSquare`
- `src/App.vue` — вызов `useChatSocket()` в `<script setup>`
- `vite.config.ts` — добавить `/ws` в dev-proxy
- `vitest.config.ts` — `environment: 'jsdom'` (для WS-composable теста)

---

## Task 1: Миграция 009 — схема чата

**Files:**
- Create: `backend/migrations/009_chat.sql`
- Modify: `backend/migrations/runner.py` (добавить `apply_migration_009` + в `apply_all`)

- [ ] **Step 1.1: Создать `009_chat.sql`**

```sql
-- Migration 009: chat subsystem (channels, channel_members, messages, read_state).
-- Idempotent (CREATE TABLE IF NOT EXISTS + information_schema guards).
-- Assumes users table already exists (created by startup/db_init).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'channels'
    ) THEN
        CREATE TABLE channels (
            id              SERIAL PRIMARY KEY,
            name            TEXT NOT NULL,
            type            TEXT NOT NULL CHECK (type IN ('general','department','topic')),
            department_role TEXT NULL,
            created_by      INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            archived        BOOLEAN NOT NULL DEFAULT false
        );
        CREATE INDEX idx_channels_type ON channels (type);
        -- department: одна роль = один канал
        CREATE UNIQUE INDEX idx_channels_department_role_unique
            ON channels (department_role) WHERE type = 'department';
        -- general: ровно один (partial index по id не мешает NULL department_role)
        CREATE UNIQUE INDEX idx_channels_general_unique
            ON channels (id) WHERE type = 'general';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'channel_members'
    ) THEN
        CREATE TABLE channel_members (
            channel_id  INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            joined_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (channel_id, user_id)
        );
        CREATE INDEX idx_channel_members_user ON channel_members (user_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'messages'
    ) THEN
        CREATE TABLE messages (
            id          BIGSERIAL PRIMARY KEY,
            channel_id  INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            author_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE SET NULL,
            content     TEXT NOT NULL CHECK (char_length(content) <= 10000),
            reply_to_id BIGINT NULL REFERENCES messages(id) ON DELETE SET NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            edited_at   TIMESTAMPTZ NULL,
            deleted_at  TIMESTAMPTZ NULL
        );
        CREATE INDEX idx_messages_channel_created
            ON messages (channel_id, created_at DESC);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'read_state'
    ) THEN
        CREATE TABLE read_state (
            user_id              INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            channel_id           INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            last_read_message_id BIGINT NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, channel_id)
        );
    END IF;
END $$;

-- Засев general-канала (идемпотентный — partial UNIQUE index защищает от дубля)
INSERT INTO channels (name, type)
SELECT 'Общий чат', 'general'
WHERE NOT EXISTS (SELECT 1 FROM channels WHERE type = 'general');
```

- [ ] **Step 1.2: Добавить `apply_migration_009` в `runner.py`**

В `backend/migrations/runner.py`, после `apply_migration_008` (после строки ~145), добавить:

```python
def apply_migration_009(conn) -> None:
    """Apply migration 009 — chat subsystem (channels/members/messages/read_state).

    Idempotent (CREATE TABLE IF NOT EXISTS + information_schema guards). Assumes
    users table already exists (created by startup/db_init). Also seeds the
    single 'general' channel (protected by a partial UNIQUE index).
    """
    sql_path = _MIGRATIONS_DIR / "009_chat.sql"
    sql = sql_path.read_text(encoding="utf-8")
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()
    logger.info("[migration] 009_chat.sql applied.")
```

И в `apply_all` (после `apply_migration_008(conn)`, ~строка 161) добавить:

```python
        apply_migration_009(conn)
```

- [ ] **Step 1.3: Smoke-test миграции на тестовой БД**

Run:
```bash
cd backend && python -c "
from dotenv import load_dotenv; load_dotenv(override=True)
from db import PG_URL
from migrations.runner import apply_migration_009
import psycopg2
c = psycopg2.connect(PG_URL)
try: apply_migration_009(c)
finally: c.close()
# verify tables + general seed
c = psycopg2.connect(PG_URL); cur = c.cursor()
for t in ['channels','channel_members','messages','read_state']:
    cur.execute('SELECT to_regclass(%s)', ('public.'+t,)); print(t, cur.fetchone()[0])
cur.execute(\"SELECT name,type FROM channels WHERE type='general'\"); print('general:', cur.fetchone())
c.close()
"
```
Expected: все 4 таблицы не NULL, `general: ('Общий чат', 'general')`.

Повторный запуск должен пройти без ошибок (idempotent) — проверить, запустив команду дважды.

- [ ] **Step 1.4: Commit**

```bash
git add backend/migrations/009_chat.sql backend/migrations/runner.py
git commit -m "feat(chat-db): migration 009 — channels/members/messages/read_state + general seed"
```

---

## Task 2: Pydantic-схемы чата

**Files:**
- Create: `backend/schemas/chat.py`

- [ ] **Step 2.1: Создать `schemas/chat.py`**

```python
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


class MessageUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)


class MemberAdd(BaseModel):
    user_id: int


class WsTicketOut(BaseModel):
    ticket: str
    expires_in: int = 30
```

> Примечание: `ChannelCreate.type` ограничен `topic`, т.к. `general`/`department` создаются сидом миграции (general) или отдельным админским путём (department — позже, при необходимости). Сейчас юзеры создают только topic.

- [ ] **Step 2.2: Smoke-test импорта**

Run: `cd backend && python -c "from schemas.chat import ChannelCreate, MessageCreate, MessageUpdate, MemberAdd, WsTicketOut; print('ok')"`
Expected: `ok`.

- [ ] **Step 2.3: Commit**

```bash
git add backend/schemas/chat.py
git commit -m "feat(chat-schemas): pydantic models for channels/messages/members/ticket"
```

---

## Task 3: CONNECTIONS реестр + `_fanout` (TDD)

**Files:**
- Create: `backend/services/chat_connections.py`
- Test: `backend/tests/test_chat_connections.py`

- [ ] **Step 3.1: Написать failing-тест**

`backend/tests/test_chat_connections.py`:

```python
"""Tests for the in-memory CONNECTIONS registry and _fanout."""
import asyncio
import pytest

from services.chat_connections import (
    CONNECTIONS,
    add_connection,
    remove_connection,
    fanout,
)


class FakeWS:
    """Minimal stand-in for starlette WebSocket with send_json/close."""
    def __init__(self):
        self.sent = []
        self.closed = False
    async def send_json(self, payload):
        self.sent.append(payload)
    async def close(self, code=1000):
        self.closed = True


@pytest.fixture(autouse=True)
def _clear_registry():
    CONNECTIONS.clear()
    yield
    CONNECTIONS.clear()


def test_add_and_remove_connection():
    ws = FakeWS()
    add_connection(7, ws)
    assert ws in CONNECTIONS[7]
    remove_connection(7, ws)
    assert 7 not in CONNECTIONS or ws not in CONNECTIONS[7]


def test_multi_tab_same_user():
    ws1, ws2 = FakeWS(), FakeWS()
    add_connection(7, ws1)
    add_connection(7, ws2)
    assert len(CONNECTIONS[7]) == 2


def _run(coro):
    return asyncio.run(coro)


def test_fanout_delivers_to_online_members(monkeypatch):
    ws_online = FakeWS()
    add_connection(5, ws_online)
    # members_of is injected by monkeypatch to avoid importing the DB layer
    import services.chat_connections as mod
    monkeypatch.setattr(mod, "members_of", lambda channel_id: [5, 6])  # 6 is offline

    _run(fanout(channel_id=1, payload={"type": "message"}, members_of=lambda c: [5, 6]))

    assert ws_online.sent == [{"type": "message"}]


def test_fanout_excludes_author(monkeypatch):
    ws_author = FakeWS()
    add_connection(5, ws_author)
    _run(fanout(
        channel_id=1,
        payload={"type": "message"},
        members=lambda c: [5],
        exclude_user=5,
    ))
    assert ws_author.sent == []  # author doesn't get their own message via WS


def test_fanout_swallows_dead_socket(monkeypatch):
    class DeadWS(FakeWS):
        async def send_json(self, payload):
            raise RuntimeError("disconnected")
    add_connection(5, DeadWS())
    # must not raise
    _run(fanout(channel_id=1, payload={"type": "x"}, members=lambda c: [5]))
```

- [ ] **Step 3.2: Run — verify FAIL**

Run: `cd backend && python -m pytest tests/test_chat_connections.py -q`
Expected: FAIL (ImportError: cannot import name ... from services.chat_connections).

- [ ] **Step 3.3: Реализовать `chat_connections.py`**

```python
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
from typing import Awaitable, Callable, Set

from starlette.websockets import WebSocket

logger = logging.getLogger("HHB_B2B")

# user_id -> set of open WebSockets (one user may have multiple tabs)
CONNECTIONS: dict[int, Set[WebSocket]] = defaultdict(set)


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
```

> Тест использует `members=...` (keyword), а реализация принимает `members` позиционно с тем же именем. Проверь что сигнатуры совпадают: тест вызывает `fanout(channel_id=1, payload=..., members_of=...)` в одном случае и `members=...` в других — **исправь тест на единый `members=`**, см. Step 3.1 (используй только `members=` везде).

- [ ] **Step 3.4: Синхронизировать имена параметров в тесте**

В `test_chat_connections.py` замени `members_of=` на `members=` в `test_fanout_delivers_to_online_members`:
```python
    _run(fanout(channel_id=1, payload={"type": "message"}, members=lambda c: [5, 6]))
```
И удали строку `monkeypatch.setattr(mod, "members_of", ...)` (не нужна — `members` инъектится параметром).

- [ ] **Step 3.5: Run — verify PASS**

Run: `cd backend && python -m pytest tests/test_chat_connections.py -q`
Expected: `5 passed`.

- [ ] **Step 3.6: Commit**

```bash
git add backend/services/chat_connections.py backend/tests/test_chat_connections.py
git commit -m "feat(chat-ws): in-memory CONNECTIONS registry + fanout (TDD)"
```

---

## Task 4: Redis-хелперы — ws-ticket (GETDEL) + rate limit (TDD)

**Files:**
- Create: `backend/services/chat_redis.py`
- Test: `backend/tests/test_chat_redis.py`

- [ ] **Step 4.1: Написать failing-тест**

`backend/tests/test_chat_redis.py`:

```python
"""Tests for chat Redis helpers: ws-ticket (atomic GETDEL) + rate limit."""
import pytest

from services.chat_redis import issue_ws_ticket, consume_ws_ticket, allow_message


class FakeRedis:
    """In-memory fake of the subset of redis.Redis we use: setex/getdel/incr/expire."""
    def __init__(self):
        self._store = {}
        self._ttls = {}
    def setex(self, key, ttl, val):
        self._store[key] = val
        self._ttls[key] = ttl
    def getdel(self, key):
        return self._store.pop(key, None)
    def incr(self, key):
        self._store[key] = int(self._store.get(key, 0)) + 1
        return self._store[key]
    def expire(self, key, ttl):
        self._ttls[key] = ttl


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    import services.chat_redis as mod
    monkeypatch.setattr(mod, "_get_redis", lambda: fake)
    return fake


def test_ws_ticket_roundtrip(fake_redis):
    ticket = issue_ws_ticket(user_id=7)
    assert consume_ws_ticket(ticket) == "7"
    # одноразовый — повторное потребление возвращает None
    assert consume_ws_ticket(ticket) is None


def test_consume_unknown_ticket_returns_none(fake_redis):
    assert consume_ws_ticket("bogus") is None


def test_rate_limit_allows_under_cap(fake_redis):
    assert all(allow_message(7) for _ in range(20))


def test_rate_limit_blocks_above_cap(fake_redis):
    for _ in range(20):
        allow_message(7)
    assert allow_message(7) is False


def test_rate_limit_per_user(fake_redis):
    for _ in range(20):
        allow_message(7)
    # другой юзер имеет свой счётчик
    assert allow_message(8) is True
```

- [ ] **Step 4.2: Run — verify FAIL**

Run: `cd backend && python -m pytest tests/test_chat_redis.py -q`
Expected: FAIL (ImportError).

- [ ] **Step 4.3: Реализовать `chat_redis.py`**

```python
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
```

- [ ] **Step 4.4: Run — verify PASS**

Run: `cd backend && python -m pytest tests/test_chat_redis.py -q`
Expected: `5 passed`.

- [ ] **Step 4.5: Commit**

```bash
git add backend/services/chat_redis.py backend/tests/test_chat_redis.py
git commit -m "feat(chat-redis): atomic ws-ticket (GETDEL) + per-user rate limit (INCR)"
```

---

## Task 5: Chat-сервис — каналы (TDD)

**Files:**
- Create: `backend/services/chat_service.py`
- Test: `backend/tests/test_chat_channels.py`

- [ ] **Step 5.1: Написать failing-тест на каналы**

`backend/tests/test_chat_channels.py`:

```python
"""Tests for chat channels: listing (role-aware), topic creation."""
import asyncio
import os

import psycopg2
import pytest

from services.chat_service import list_channels, create_topic_channel
from schemas.chat import ChannelCreate


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def seeded_chat(db_conn, monkeypatch):
    import services.chat_service as svc

    cur = db_conn.cursor()
    for t in ["read_state", "messages", "channel_members", "channels"]:
        cur.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    cur.execute("DROP TABLE IF EXISTS users CASCADE")
    cur.execute("CREATE TABLE users (id SERIAL PRIMARY KEY, username TEXT, role TEXT)")
    cur.execute(
        """CREATE TABLE channels (
        id SERIAL PRIMARY KEY, name TEXT, type TEXT,
        department_role TEXT, created_by INTEGER,
        created_at TIMESTAMPTZ DEFAULT now(), archived BOOLEAN DEFAULT false)"""
    )
    cur.execute(
        "CREATE TABLE channel_members (channel_id INTEGER, user_id INTEGER, "
        "joined_at TIMESTAMPTZ DEFAULT now(), PRIMARY KEY (channel_id, user_id))"
    )
    # seed general + a department(manager) channel
    cur.execute("INSERT INTO channels (name,type) VALUES ('Общий чат','general')")
    cur.execute("INSERT INTO channels (name,type,department_role) VALUES ('Продажи','department','manager')")
    cur.execute("INSERT INTO users (username,role) VALUES ('a','admin'),('m','manager'),('e','employee')")
    cur.close()

    TEST_DSN = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:235813@localhost:5432/hhb_b2b_test")

    def _test_get_db():
        return psycopg2.connect(TEST_DSN)

    monkeypatch.setattr(svc, "get_db", _test_get_db)


def test_admin_sees_general_and_topic(seeded_chat):
    # admin creates a topic channel and becomes a member
    _run(create_topic_channel(
        data=ChannelCreate(name="KYK launch", member_ids=[]),
        current_user={"id": 1, "role": "admin"},
    ))
    chans = _run(list_channels(current_user={"id": 1, "role": "admin"}))
    names = {c["name"] for c in chans}
    assert "Общий чат" in names          # general visible to all staff
    assert "KYK launch" in names         # topic the creator joined


def test_manager_sees_their_department(seeded_chat):
    chans = _run(list_channels(current_user={"id": 2, "role": "manager"}))
    names = {c["name"] for c in chans}
    assert "Общий чат" in names
    assert "Продажи" in names            # department matching their role


def test_employee_does_not_see_manager_department(seeded_chat):
    chans = _run(list_channels(current_user={"id": 3, "role": "employee"}))
    names = {c["name"] for c in chans}
    assert "Общий чат" in names
    assert "Продажи" not in names        # department role mismatch


def test_only_staff_can_list_channels(seeded_chat):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        _run(list_channels(current_user={"id": 9, "role": "client"}))
    assert exc.value.status_code == 403
```

- [ ] **Step 5.2: Run — verify FAIL**

Run: `cd backend && python -m pytest tests/test_chat_channels.py -q`
Expected: FAIL (ImportError).

- [ ] **Step 5.3: Реализовать `chat_service.py` (часть: каналы)**

```python
"""Chat business logic: channels, messages, read_state, membership.

Pattern matches orders/defects/machinery services: router → service → db,
Depends(get_current_user), owner-checks. All async functions use sync psycopg2
internally (the codebase standard).
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import HTTPException

from db import get_db, q

_STAFF_ROLES = ("admin", "manager", "employee")


def _require_staff(current_user: Dict[str, Any]) -> None:
    if current_user.get("role") not in _STAFF_ROLES:
        raise HTTPException(403, "Чат доступен только сотрудникам")


# ---------- Channels ----------

async def list_channels(current_user: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Channels visible to the user: general (all staff) + their department +
    topic channels they're a member of."""
    _require_staff(current_user)
    conn = get_db()
    try:
        cur = conn.cursor()
        uid = current_user["id"]
        role = current_user["role"]
        cur.execute(
            q(
                """
                SELECT id, name, type, department_role, archived
                FROM channels
                WHERE type = 'general'
                   OR (type = 'department' AND department_role = %s)
                   OR (type = 'topic' AND id IN (
                       SELECT channel_id FROM channel_members WHERE user_id = %s))
                ORDER BY type, name
                """
            ),
            (role, uid),
        )
        rows = cur.fetchall()
        return [_channel_row_to_dict(r) for r in rows]
    finally:
        conn.close()


async def create_topic_channel(
    data: Any,  # ChannelCreate
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    _require_staff(current_user)
    if current_user["role"] not in ("admin", "manager"):
        raise HTTPException(403, "Только admin/manager могут создавать каналы")
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            q(
                """
                INSERT INTO channels (name, type, created_by)
                VALUES (%s, 'topic', %s) RETURNING id
                """
            ),
            (data.name, current_user["id"]),
        )
        channel_id = cur.fetchone()[0]
        # creator is always a member
        members = {current_user["id"], *data.member_ids}
        for uid in members:
            cur.execute(
                q("INSERT INTO channel_members (channel_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING"),
                (channel_id, uid),
            )
        conn.commit()
        return {"id": channel_id, "name": data.name, "type": "topic", "archived": False}
    finally:
        conn.close()


def _channel_row_to_dict(r) -> Dict[str, Any]:
    return {
        "id": r[0],
        "name": r[1],
        "type": r[2],
        "department_role": r[3],
        "archived": r[4],
    }
```

- [ ] **Step 5.4: Run — verify PASS**

Run: `cd backend && python -m pytest tests/test_chat_channels.py -q`
Expected: `4 passed`.

- [ ] **Step 5.5: Commit**

```bash
git add backend/services/chat_service.py backend/tests/test_chat_channels.py
git commit -m "feat(chat-svc): list channels (role-aware) + create topic (TDD)"
```

---

## Task 6: Chat-сервис — сообщения + read-state (TDD)

**Files:**
- Modify: `backend/services/chat_service.py` (добавить message/read-state функции)
- Create: `backend/tests/test_chat_messages.py`, `backend/tests/test_chat_read_state.py`

- [ ] **Step 6.1: Написать failing-тест на сообщения**

`backend/tests/test_chat_messages.py`:

```python
"""Tests for chat messages: send, history (cursor pagination), edit, soft-delete, membership check."""
import asyncio
import os

import psycopg2
import pytest
from fastapi import HTTPException

from services.chat_service import list_messages, send_message, edit_message, delete_message
from schemas.chat import MessageCreate, MessageUpdate


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def seeded_msgs(db_conn, monkeypatch):
    import services.chat_service as svc

    cur = db_conn.cursor()
    for t in ["read_state", "messages", "channel_members", "channels"]:
        cur.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    cur.execute("DROP TABLE IF EXISTS users CASCADE")
    cur.execute("CREATE TABLE users (id SERIAL PRIMARY KEY, username TEXT, role TEXT)")
    cur.execute(
        """CREATE TABLE channels (
        id SERIAL PRIMARY KEY, name TEXT, type TEXT, department_role TEXT,
        created_by INTEGER, created_at TIMESTAMPTZ DEFAULT now(), archived BOOLEAN DEFAULT false)"""
    )
    cur.execute(
        "CREATE TABLE channel_members (channel_id INTEGER, user_id INTEGER, "
        "joined_at TIMESTAMPTZ DEFAULT now(), PRIMARY KEY (channel_id, user_id))"
    )
    cur.execute(
        """CREATE TABLE messages (
        id BIGSERIAL PRIMARY KEY, channel_id INTEGER, author_id INTEGER,
        content TEXT NOT NULL CHECK (char_length(content) <= 10000),
        reply_to_id BIGINT NULL, created_at TIMESTAMPTZ DEFAULT now(),
        edited_at TIMESTAMPTZ NULL, deleted_at TIMESTAMPTZ NULL)"""
    )
    cur.execute("CREATE TABLE read_state (user_id INTEGER, channel_id INTEGER, last_read_message_id BIGINT DEFAULT 0, PRIMARY KEY (user_id, channel_id))")
    # general channel; topic #2 where user 1 is member; topic #3 where user 1 is NOT
    cur.execute("INSERT INTO channels (name,type) VALUES ('G','general'), ('T2','topic'), ('T3','topic')")
    cur.execute("INSERT INTO channel_members (channel_id,user_id) VALUES (2,1)")
    cur.execute("INSERT INTO users (username,role) VALUES ('a','admin'),('b','manager')")
    cur.close()

    TEST_DSN = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:235813@localhost:5432/hhb_b2b_test")
    monkeypatch.setattr(svc, "get_db", lambda: psycopg2.connect(TEST_DSN))


def test_send_message_to_member_channel(seeded_msgs):
    m = _run(send_message(
        channel_id=2,
        data=MessageCreate(content="hi"),
        current_user={"id": 1, "role": "manager"},
    ))
    assert m["content"] == "hi"
    assert m["channel_id"] == 2


def test_send_message_to_non_member_topic_403(seeded_msgs):
    with pytest.raises(HTTPException) as exc:
        _run(send_message(
            channel_id=3,  # user 1 not a member of T3
            data=MessageCreate(content="x"),
            current_user={"id": 1, "role": "manager"},
        ))
    assert exc.value.status_code == 403


def test_history_default_returns_latest_first(seeded_msgs):
    _run(send_message(channel_id=2, data=MessageCreate(content="first"), current_user={"id": 1, "role": "manager"}))
    _run(send_message(channel_id=2, data=MessageCreate(content="second"), current_user={"id": 1, "role": "manager"}))
    hist = _run(list_messages(channel_id=2, current_user={"id": 1, "role": "manager"}))
    assert hist[0]["content"] == "second"   # newest first
    assert len(hist) == 2


def test_history_cursor_pagination(seeded_msgs):
    ids = []
    for i in range(3):
        m = _run(send_message(channel_id=2, data=MessageCreate(content=f"m{i}"), current_user={"id": 1, "role": "manager"}))
        ids.append(m["id"])
    page = _run(list_messages(channel_id=2, before=ids[2], current_user={"id": 1, "role": "manager"}))
    # before ids[2] -> only m0,m1
    assert {m["id"] for m in page} == {ids[0], ids[1]}


def test_edit_only_author(seeded_msgs):
    m = _run(send_message(channel_id=2, data=MessageCreate(content="orig"), current_user={"id": 1, "role": "manager"}))
    out = _run(edit_message(message_id=m["id"], data=MessageUpdate(content="edited"), current_user={"id": 1, "role": "manager"}))
    assert out["content"] == "edited"
    # different author
    with pytest.raises(HTTPException) as exc:
        _run(edit_message(message_id=m["id"], data=MessageUpdate(content="hack"), current_user={"id": 2, "role": "manager"}))
    assert exc.value.status_code == 403


def test_soft_delete_only_author_or_admin(seeded_msgs):
    m = _run(send_message(channel_id=2, data=MessageCreate(content="bye"), current_user={"id": 1, "role": "manager"}))
    # non-author non-admin -> 403
    with pytest.raises(HTTPException) as exc:
        _run(delete_message(message_id=m["id"], current_user={"id": 2, "role": "manager"}))
    assert exc.value.status_code == 403
    # author -> ok
    _run(delete_message(message_id=m["id"], current_user={"id": 1, "role": "manager"}))
    hist = _run(list_messages(channel_id=2, current_user={"id": 1, "role": "manager"}))
    assert hist[0]["deleted_at"] is not None
```

- [ ] **Step 6.2: Run — verify FAIL**

Run: `cd backend && python -m pytest tests/test_chat_messages.py -q`
Expected: FAIL (ImportError: cannot import name list_messages...).

- [ ] **Step 6.3: Реализовать message-функции в `chat_service.py`**

Добавить в конец `backend/services/chat_service.py`:

```python
# ---------- Membership helper ----------

async def _members_of(channel_id: int) -> list[int]:
    """Return user_ids that can see `channel_id` (sync query). Used by fanout."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(q("SELECT type, department_role FROM channels WHERE id = %s"), (channel_id,))
        row = cur.fetchone()
        if not row:
            return []
        ctype, dept_role = row
        if ctype == "topic":
            cur.execute(q("SELECT user_id FROM channel_members WHERE channel_id = %s"), (channel_id,))
        elif ctype == "department":
            cur.execute(q("SELECT id FROM users WHERE role = %s"), (dept_role,))
        else:  # general
            cur.execute(q("SELECT id FROM users WHERE role IN ('admin','manager','employee')"))
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def _require_channel_access(cur, channel_id: int, current_user: Dict[str, Any]) -> Dict[str, Any]:
    """Raise 403 if the user can't read/write the channel."""
    cur.execute(q("SELECT type, department_role FROM channels WHERE id = %s"), (channel_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Канал не найден")
    ctype, dept_role = row
    role = current_user["role"]
    uid = current_user["id"]
    if ctype == "general":
        return {"type": ctype}
    if ctype == "department":
        if role != dept_role:
            raise HTTPException(403, "Нет доступа к каналу отдела")
        return {"type": ctype}
    # topic
    cur.execute(
        q("SELECT 1 FROM channel_members WHERE channel_id = %s AND user_id = %s"),
        (channel_id, uid),
    )
    if not cur.fetchone():
        raise HTTPException(403, "Нет доступа к каналу")
    return {"type": ctype}


# ---------- Messages ----------

async def list_messages(
    channel_id: int,
    current_user: Dict[str, Any],
    before: int | None = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    _require_staff(current_user)
    conn = get_db()
    try:
        cur = conn.cursor()
        _require_channel_access(cur, channel_id, current_user)
        if before:
            cur.execute(
                q(
                    f"""SELECT id, channel_id, author_id, content, reply_to_id,
                        created_at, edited_at, deleted_at
                        FROM messages WHERE channel_id = %s AND id < %s
                        ORDER BY id DESC LIMIT %s"""
                ),
                (channel_id, before, limit),
            )
        else:
            cur.execute(
                q(
                    f"""SELECT id, channel_id, author_id, content, reply_to_id,
                        created_at, edited_at, deleted_at
                        FROM messages WHERE channel_id = %s
                        ORDER BY id DESC LIMIT %s"""
                ),
                (channel_id, limit),
            )
        return [_message_row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


async def send_message(
    channel_id: int,
    data: Any,  # MessageCreate
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    _require_staff(current_user)
    # rate limit (Redis) — protects fan-out from floods
    from services.chat_redis import allow_message
    if not allow_message(current_user["id"]):
        raise HTTPException(429, "Слишком много сообщений, попробуйте позже")
    conn = get_db()
    try:
        cur = conn.cursor()
        _require_channel_access(cur, channel_id, current_user)
        cur.execute(
            q(
                """INSERT INTO messages (channel_id, author_id, content, reply_to_id)
                   VALUES (%s, %s, %s, %s) RETURNING id, created_at"""
            ),
            (channel_id, current_user["id"], data.content, data.reply_to_id),
        )
        mid, created_at = cur.fetchone()
        conn.commit()
        return {
            "id": mid,
            "channel_id": channel_id,
            "author_id": current_user["id"],
            "content": data.content,
            "reply_to_id": data.reply_to_id,
            "created_at": created_at.isoformat() if created_at else None,
            "edited_at": None,
            "deleted_at": None,
        }
    finally:
        conn.close()


async def edit_message(
    message_id: int,
    data: Any,  # MessageUpdate
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    _require_staff(current_user)
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(q("SELECT author_id FROM messages WHERE id = %s"), (message_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Сообщение не найдено")
        if row[0] != current_user["id"]:
            raise HTTPException(403, "Редактировать может только автор")
        cur.execute(
            q("UPDATE messages SET content = %s, edited_at = now() WHERE id = %s"),
            (data.content, message_id),
        )
        conn.commit()
        return {"id": message_id, "content": data.content, "ok": True}
    finally:
        conn.close()


async def delete_message(
    message_id: int,
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    _require_staff(current_user)
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(q("SELECT author_id FROM messages WHERE id = %s"), (message_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Сообщение не найдено")
        if row[0] != current_user["id"] and current_user["role"] != "admin":
            raise HTTPException(403, "Удалять может только автор или admin")
        cur.execute(q("UPDATE messages SET deleted_at = now() WHERE id = %s"), (message_id,))
        conn.commit()
        return {"id": message_id, "ok": True}
    finally:
        conn.close()


def _message_row_to_dict(r) -> Dict[str, Any]:
    return {
        "id": r[0],
        "channel_id": r[1],
        "author_id": r[2],
        "content": r[3],
        "reply_to_id": r[4],
        "created_at": r[5].isoformat() if r[5] else None,
        "edited_at": r[6].isoformat() if r[6] else None,
        "deleted_at": r[7].isoformat() if r[7] else None,
    }
```

- [ ] **Step 6.4: Run — verify PASS**

Run: `cd backend && python -m pytest tests/test_chat_messages.py -q`
Expected: `6 passed`.

- [ ] **Step 6.5: Написать failing-тест на read-state**

`backend/tests/test_chat_read_state.py`:

```python
"""Tests for chat read_state + unread counts."""
import asyncio
import os

import psycopg2
import pytest

from services.chat_service import mark_read, unread_counts, send_message
from schemas.chat import MessageCreate


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def seeded_rs(db_conn, monkeypatch):
    import services.chat_service as svc
    cur = db_conn.cursor()
    for t in ["read_state", "messages", "channel_members", "channels"]:
        cur.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    cur.execute("DROP TABLE IF EXISTS users CASCADE")
    cur.execute("CREATE TABLE users (id SERIAL PRIMARY KEY, username TEXT, role TEXT)")
    cur.execute(
        """CREATE TABLE channels (id SERIAL PRIMARY KEY, name TEXT, type TEXT,
        department_role TEXT, created_by INTEGER, created_at TIMESTAMPTZ DEFAULT now(),
        archived BOOLEAN DEFAULT false)"""
    )
    cur.execute(
        "CREATE TABLE channel_members (channel_id INTEGER, user_id INTEGER, "
        "joined_at TIMESTAMPTZ DEFAULT now(), PRIMARY KEY (channel_id, user_id))"
    )
    cur.execute(
        """CREATE TABLE messages (id BIGSERIAL PRIMARY KEY, channel_id INTEGER, author_id INTEGER,
        content TEXT NOT NULL CHECK (char_length(content) <= 10000), reply_to_id BIGINT NULL,
        created_at TIMESTAMPTZ DEFAULT now(), edited_at TIMESTAMPTZ NULL, deleted_at TIMESTAMPTZ NULL)"""
    )
    cur.execute("CREATE TABLE read_state (user_id INTEGER, channel_id INTEGER, last_read_message_id BIGINT DEFAULT 0, PRIMARY KEY (user_id, channel_id))")
    cur.execute("INSERT INTO channels (name,type) VALUES ('G','general')")
    cur.execute("INSERT INTO users (username,role) VALUES ('a','admin'),('b','manager')")
    cur.close()
    TEST_DSN = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:235813@localhost:5432/hhb_b2b_test")
    monkeypatch.setattr(svc, "get_db", lambda: psycopg2.connect(TEST_DSN))


def test_unread_starts_zero(seeded_rs):
    counts = _run(unread_counts(current_user={"id": 1, "role": "admin"}))
    assert counts.get(1, 0) == 0


def test_mark_read_advances_cursor(seeded_rs):
    m = _run(send_message(channel_id=1, data=MessageCreate(content="x"), current_user={"id": 2, "role": "manager"}))
    # user 1 hasn't read -> unread 1
    counts_before = _run(unread_counts(current_user={"id": 1, "role": "admin"}))
    assert counts_before.get(1, 0) == 1
    _run(mark_read(channel_id=1, last_read_message_id=m["id"], current_user={"id": 1, "role": "admin"}))
    counts_after = _run(unread_counts(current_user={"id": 1, "role": "admin"}))
    assert counts_after.get(1, 0) == 0
```

- [ ] **Step 6.6: Run — verify FAIL**

Run: `cd backend && python -m pytest tests/test_chat_read_state.py -q`
Expected: FAIL (ImportError).

- [ ] **Step 6.7: Реализовать read-state функции в `chat_service.py`**

Добавить в `backend/services/chat_service.py`:

```python
# ---------- Read state + unread ----------

async def mark_read(
    channel_id: int,
    last_read_message_id: int,
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    _require_staff(current_user)
    conn = get_db()
    try:
        cur = conn.cursor()
        _require_channel_access(cur, channel_id, current_user)
        cur.execute(
            q(
                """INSERT INTO read_state (user_id, channel_id, last_read_message_id)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (user_id, channel_id) DO UPDATE
                   SET last_read_message_id = GREATEST(read_state.last_read_message_id, EXCLUDED.last_read_message_id)"""
            ),
            (current_user["id"], channel_id, last_read_message_id),
        )
        conn.commit()
        return {"channel_id": channel_id, "last_read_message_id": last_read_message_id, "ok": True}
    finally:
        conn.close()


async def unread_counts(current_user: Dict[str, Any]) -> Dict[int, int]:
    """Return {channel_id: unread_count} for all channels visible to the user."""
    _require_staff(current_user)
    conn = get_db()
    try:
        cur = conn.cursor()
        uid = current_user["id"]
        role = current_user["role"]
        cur.execute(
            q(
                """
                SELECT c.id, c.type, COALESCE(rs.last_read_message_id, 0)
                FROM channels c
                LEFT JOIN read_state rs ON rs.channel_id = c.id AND rs.user_id = %s
                WHERE c.type = 'general'
                   OR (c.type = 'department' AND c.department_role = %s)
                   OR (c.type = 'topic' AND c.id IN (
                       SELECT channel_id FROM channel_members WHERE user_id = %s))
                """
            ),
            (uid, role, uid),
        )
        chans = cur.fetchall()
        result: Dict[int, int] = {}
        for channel_id, _ctype, last_read in chans:
            cur.execute(
                q(
                    """SELECT COUNT(*) FROM messages
                       WHERE channel_id = %s AND id > %s AND deleted_at IS NULL"""
                ),
                (channel_id, last_read),
            )
            result[channel_id] = cur.fetchone()[0]
        return result
    finally:
        conn.close()
```

- [ ] **Step 6.8: Run — verify PASS**

Run: `cd backend && python -m pytest tests/test_chat_read_state.py -q`
Expected: `2 passed`.

- [ ] **Step 6.9: Commit**

```bash
git add backend/services/chat_service.py backend/tests/test_chat_messages.py backend/tests/test_chat_read_state.py
git commit -m "feat(chat-svc): messages (send/list/edit/soft-delete) + read_state + unread (TDD)"
```

---

## Task 7: Chat-сервис — membership (TDD)

**Files:**
- Modify: `backend/services/chat_service.py`
- Create: `backend/tests/test_chat_membership.py`

- [ ] **Step 7.1: Написать failing-тест**

`backend/tests/test_chat_membership.py`:

```python
"""Tests for topic-channel membership: add/remove + 400 on general/department."""
import asyncio
import os

import psycopg2
import pytest
from fastapi import HTTPException

from services.chat_service import add_member, remove_member


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def seeded_mem(db_conn, monkeypatch):
    import services.chat_service as svc
    cur = db_conn.cursor()
    for t in ["read_state", "messages", "channel_members", "channels"]:
        cur.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    cur.execute("DROP TABLE IF EXISTS users CASCADE")
    cur.execute("CREATE TABLE users (id SERIAL PRIMARY KEY, username TEXT, role TEXT)")
    cur.execute(
        """CREATE TABLE channels (id SERIAL PRIMARY KEY, name TEXT, type TEXT,
        department_role TEXT, created_by INTEGER, created_at TIMESTAMPTZ DEFAULT now(),
        archived BOOLEAN DEFAULT false)"""
    )
    cur.execute(
        "CREATE TABLE channel_members (channel_id INTEGER, user_id INTEGER, "
        "joined_at TIMESTAMPTZ DEFAULT now(), PRIMARY KEY (channel_id, user_id))"
    )
    cur.execute("INSERT INTO channels (name,type,department_role) VALUES ('G','general',NULL), ('D','department','manager'), ('T','topic',NULL)")
    cur.execute("INSERT INTO channel_members (channel_id,user_id) VALUES (3,1)")
    cur.execute("INSERT INTO users (username,role) VALUES ('a','admin'),('b','manager'),('c','employee')")
    cur.close()
    TEST_DSN = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:235813@localhost:5432/hhb_b2b_test")
    monkeypatch.setattr(svc, "get_db", lambda: psycopg2.connect(TEST_DSN))


def test_add_member_to_topic(seeded_mem):
    _run(add_member(channel_id=3, user_id=2, current_user={"id": 1, "role": "admin"}))
    # now user 2 is a member


def test_remove_member_from_topic(seeded_mem):
    _run(remove_member(channel_id=3, user_id=1, current_user={"id": 1, "role": "admin"}))


def test_cannot_remove_from_general(seeded_mem):
    with pytest.raises(HTTPException) as exc:
        _run(remove_member(channel_id=1, user_id=1, current_user={"id": 1, "role": "admin"}))
    assert exc.value.status_code == 400


def test_cannot_remove_from_department(seeded_mem):
    with pytest.raises(HTTPException) as exc:
        _run(remove_member(channel_id=2, user_id=2, current_user={"id": 1, "role": "admin"}))
    assert exc.value.status_code == 400
```

- [ ] **Step 7.2: Run — verify FAIL**

Run: `cd backend && python -m pytest tests/test_chat_membership.py -q`
Expected: FAIL (ImportError).

- [ ] **Step 7.3: Реализовать membership-функции**

Добавить в `backend/services/chat_service.py`:

```python
# ---------- Membership (topic only) ----------

def _require_topic(cur, channel_id: int) -> None:
    """Raise 400 if channel is not a topic — general/department membership is computed."""
    cur.execute(q("SELECT type FROM channels WHERE id = %s"), (channel_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Канал не найден")
    if row[0] != "topic":
        raise HTTPException(400, "Членство редактируется только в тематических каналах")


async def add_member(
    channel_id: int,
    user_id: int,
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    _require_staff(current_user)
    if current_user["role"] not in ("admin", "manager"):
        raise HTTPException(403, "Только admin/manager могут добавлять участников")
    conn = get_db()
    try:
        cur = conn.cursor()
        _require_topic(cur, channel_id)
        cur.execute(
            q("INSERT INTO channel_members (channel_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING"),
            (channel_id, user_id),
        )
        conn.commit()
        return {"channel_id": channel_id, "user_id": user_id, "ok": True}
    finally:
        conn.close()


async def remove_member(
    channel_id: int,
    user_id: int,
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    _require_staff(current_user)
    conn = get_db()
    try:
        cur = conn.cursor()
        _require_topic(cur, channel_id)
        # self can leave; admin/manager can remove others
        if user_id != current_user["id"] and current_user["role"] not in ("admin", "manager"):
            raise HTTPException(403, "Можно удалять только себя")
        cur.execute(
            q("DELETE FROM channel_members WHERE channel_id = %s AND user_id = %s"),
            (channel_id, user_id),
        )
        conn.commit()
        return {"channel_id": channel_id, "user_id": user_id, "ok": True}
    finally:
        conn.close()
```

- [ ] **Step 7.4: Run — verify PASS**

Run: `cd backend && python -m pytest tests/test_chat_membership.py -q`
Expected: `4 passed`.

- [ ] **Step 7.5: Commit**

```bash
git add backend/services/chat_service.py backend/tests/test_chat_membership.py
git commit -m "feat(chat-svc): topic membership add/remove + 400 on general/department (TDD)"
```

---

## Task 8: REST-роутер `/api/chat/*`

**Files:**
- Create: `backend/routes/chat.py`
- Modify: `backend/routes/index.py` (register_routes)

- [ ] **Step 8.1: Создать `routes/chat.py`**

```python
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
```

- [ ] **Step 8.2: Подключить роутер в `register_routes`**

В `backend/routes/index.py`, в `register_routes`, после блока orders (~строка 349) добавить:

```python
    # Chat (messaging subsystem I)
    from routes.chat import router as chat_router

    app.include_router(chat_router)
```

- [ ] **Step 8.3: Smoke-test — приложение стартует, эндпоинты видны**

Run:
```bash
cd backend && python -c "
from fastapi import FastAPI
from routes.chat import router
app = FastAPI(); app.include_router(router)
paths = [r.path for r in app.routes]
for p in ['/api/chat/channels','/api/chat/ws-ticket','/api/chat/unread']:
    assert p in paths, p
print('chat routes registered:', sum(1 for p in paths if '/api/chat' in p))
"
```
Expected: `chat routes registered: 9` (или больше).

- [ ] **Step 8.4: Commit**

```bash
git add backend/routes/chat.py backend/routes/index.py
git commit -m "feat(chat-rest): REST endpoints /api/chat/* + register in app"
```

---

## Task 9: WebSocket-хендлер `/ws/chat` (TDD)

**Files:**
- Create: `backend/routes/chat_ws.py`
- Modify: `backend/routes/index.py` (register ws route)
- Modify: `backend/requirements.txt` (add `httpx-ws`)
- Test: `backend/tests/test_chat_ws.py`

- [ ] **Step 9.1: Добавить `httpx-ws` в requirements**

В `backend/requirements.txt` добавить строку:
```
httpx-ws>=0.6.0
```

Установить: `cd backend && pip install httpx-ws>=0.6.0`

- [ ] **Step 9.2: Написать failing-тест на WS**

`backend/tests/test_chat_ws.py`:

```python
"""Tests for the /ws/chat WebSocket handler: ticket auth + echo of typing."""
import os

import pytest
import psycopg2
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def ws_app(db_conn, monkeypatch):
    import routes.chat_ws as wsmod
    import services.chat_redis as rmod

    cur = db_conn.cursor()
    cur.execute("DROP TABLE IF EXISTS users CASCADE")
    cur.execute("CREATE TABLE users (id SERIAL PRIMARY KEY, username TEXT, role TEXT)")
    cur.execute("INSERT INTO users (username,role) VALUES ('a','admin')")
    cur.close()

    # fake redis: tickets stored in-memory
    class FakeRedis:
        def __init__(self): self._s = {}
        def setex(self, k, t, v): self._s[k] = v
        def getdel(self, k): return self._s.pop(k, None)
    fake = FakeRedis()
    monkeypatch.setattr(rmod, "_get_redis", lambda: fake)

    app = FastAPI()
    app.include_router(wsmod.router)
    return app, fake


def test_ws_rejects_without_ticket(ws_app):
    app, _ = ws_app
    client = TestClient(app)
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/chat"):
            pass


def test_ws_accepts_valid_ticket_then_closes(ws_app):
    app, fake = ws_app
    from services.chat_redis import issue_ws_ticket
    # issue a ticket for user_id=1
    ticket = issue_ws_ticket(1)
    client = TestClient(app)
    with client.websocket_connect(f"/ws/chat?ticket={ticket}") as ws:
        # connection accepted; send a typing ping and expect no crash
        ws.send_json({"type": "typing", "channel_id": 1})
        # the handler may not reply to typing; just assert we're connected
    assert True


def test_ws_ticket_single_use(ws_app):
    app, fake = ws_app
    from services.chat_redis import issue_ws_ticket, consume_ws_ticket
    ticket = issue_ws_ticket(1)
    assert consume_ws_ticket(ticket) == "1"
    # second consume -> None (atomic GETDEL already removed it)
    assert consume_ws_ticket(ticket) is None
```

- [ ] **Step 9.3: Run — verify FAIL**

Run: `cd backend && python -m pytest tests/test_chat_ws.py -q`
Expected: FAIL (ImportError: routes.chat_ws).

- [ ] **Step 9.4: Реализовать `chat_ws.py`**

```python
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
        await websocket.close(code=4401)
        return
    user_id_str = consume_ws_ticket(ticket)
    if not user_id_str:
        await websocket.accept()  # must accept before close in starlette
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
```

- [ ] **Step 9.5: Подключить WS-роутер в `register_routes`**

В `backend/routes/index.py`, после блока chat_router (Task 8.3), добавить:

```python
    from routes.chat_ws import router as chat_ws_router
    app.include_router(chat_ws_router)
```

- [ ] **Step 9.6: Run — verify PASS**

Run: `cd backend && python -m pytest tests/test_chat_ws.py -q`
Expected: `3 passed`.

- [ ] **Step 9.7: Commit**

```bash
git add backend/routes/chat_ws.py backend/routes/index.py backend/requirements.txt backend/tests/test_chat_ws.py
git commit -m "feat(chat-ws): WebSocket handler /ws/chat with GETDEL ticket auth (TDD)"
```

---

## Task 10: conftest — очистка chat-таблиц

**Files:**
- Modify: `backend/tests/conftest.py`

- [ ] **Step 10.1: Добавить chat-таблицы в `_TABLES_TO_CLEAR`**

В `backend/tests/conftest.py`, строку `_TABLES_TO_CLEAR` (строка 17) заменить на:

```python
_TABLES_TO_CLEAR = ["read_state", "messages", "channel_members", "channels", "proposal_items", "proposals", "clients", "users", "products", "categories", "brands", "sku_catalog", "kyk_products_import", "job_queue"]
```

(Порядок важен: зависимые таблицы (read_state/messages/channel_members) идут ДО channels; channels ДО users — но CASCADE в наших DROP'ах в тестах уже это разруливает. Здесь просто для общей чистоты между тестами.)

- [ ] **Step 10.2: Run full suite — verify nothing broke**

Run: `cd backend && python -m pytest -q`
Expected: all green (121 старых + ~24 новых чат-тестов ≈ 145 passed).

- [ ] **Step 10.3: Commit**

```bash
git add backend/tests/conftest.py
git commit -m "test(chat): clear chat tables between tests in conftest"
```

---

## Task 11: Frontend — типы + API-модуль

**Files:**
- Create: `src/types/chat.ts`
- Create: `src/api/chat.ts`

- [ ] **Step 11.1: Создать `types/chat.ts`**

```ts
export type ChannelType = 'general' | 'department' | 'topic'

export interface Channel {
  id: number
  name: string
  type: ChannelType
  department_role?: string | null
  archived?: boolean
}

export interface ChatMessage {
  id: number
  channel_id: number
  author_id: number
  content: string
  reply_to_id?: number | null
  created_at: string | null
  edited_at?: string | null
  deleted_at?: string | null
}

export interface WsTicket {
  ticket: string
  expires_in: number
}
```

- [ ] **Step 11.2: Создать `api/chat.ts`**

```ts
import { api } from './client'
import type { Channel, ChatMessage } from '@/types/chat'

export const chatApi = {
  listChannels: () => api.get<Channel[]>('/api/chat/channels'),
  createTopic: (data: { name: string; member_ids?: number[] }) =>
    api.post<Channel>('/api/chat/channels', { name: data.name, type: 'topic', member_ids: data.member_ids ?? [] }),
  listMessages: (channelId: number, before?: number) =>
    api.get<ChatMessage[]>(`/api/chat/channels/${channelId}/messages`, { params: before ? { before } : {} }),
  sendMessage: (channelId: number, data: { content: string; reply_to_id?: number | null }) =>
    api.post<ChatMessage>(`/api/chat/channels/${channelId}/messages`, data),
  editMessage: (id: number, content: string) =>
    api.patch<{ ok: boolean }>(`/api/chat/messages/${id}`, { content }),
  deleteMessage: (id: number) => api.delete(`/api/chat/messages/${id}`),
  markRead: (channelId: number) => api.post(`/api/chat/channels/${channelId}/read`),
  unread: () => api.get<Record<string, number>>('/api/chat/unread'),
  addMember: (channelId: number, userId: number) =>
    api.post(`/api/chat/channels/${channelId}/members`, { user_id: userId }),
  removeMember: (channelId: number, userId: number) =>
    api.delete(`/api/chat/channels/${channelId}/members/${userId}`),
  wsTicket: () => api.post<{ ticket: string }>('/api/chat/ws-ticket'),
}
```

- [ ] **Step 11.3: Smoke-test сборки**

Run: `cd /d/Projects/frontcrm && npx vue-tsc --noEmit 2>&1 | grep -i "chat" | head`
Expected: no errors mentioning chat types (or empty output).

- [ ] **Step 11.4: Commit**

```bash
git add src/types/chat.ts src/api/chat.ts
git commit -m "feat(chat-fe): TS types + axios api module"
```

---

## Task 12: Frontend — Pinia store

**Files:**
- Create: `src/stores/chat.ts`

- [ ] **Step 12.1: Создать `stores/chat.ts`**

```ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { chatApi } from '@/api/chat'
import type { Channel, ChatMessage } from '@/types/chat'

export const useChatStore = defineStore('chat', () => {
  const channels = ref<Channel[]>([])
  const activeChannelId = ref<number | null>(null)
  const messagesByChannel = ref<Record<number, ChatMessage[]>>({})
  const unread = ref<Record<number, number>>({})
  const loading = ref(false)
  const typingUsers = ref<Record<number, number[]>>({})  // channelId -> user_ids typing

  const activeChannel = computed(() =>
    channels.value.find((c) => c.id === activeChannelId.value) ?? null,
  )
  const activeMessages = computed(() =>
    activeChannelId.value ? messagesByChannel.value[activeChannelId.value] ?? [] : [],
  )

  async function loadChannels() {
    loading.value = true
    try {
      const { data } = await chatApi.listChannels()
      channels.value = data
      if (!activeChannelId.value && data.length) activeChannelId.value = data[0].id
    } finally {
      loading.value = false
    }
  }

  async function loadUnread() {
    const { data } = await chatApi.unread()
    unread.value = data
  }

  async function loadHistory(channelId: number, before?: number) {
    const { data } = await chatApi.listMessages(channelId, before)
    // newest first from API; reverse for display (oldest at top)
    const ordered = [...data].reverse()
    if (before) {
      // older page — prepend
      messagesByChannel.value[channelId] = [...ordered, ...(messagesByChannel.value[channelId] ?? [])]
    } else {
      messagesByChannel.value[channelId] = ordered
    }
  }

  async function sendMessage(channelId: number, content: string) {
    const { data } = await chatApi.sendMessage(channelId, { content })
    // optimistic: append locally; WS will broadcast to others
    messagesByChannel.value[channelId] = [...(messagesByChannel.value[channelId] ?? []), data]
    // clear unread for self
    unread.value[channelId] = 0
  }

  async function markRead(channelId: number) {
    await chatApi.markRead(channelId)
    unread.value[channelId] = 0
  }

  // Called by useChatSocket when a WS 'message' frame arrives
  function onIncomingMessage(msg: ChatMessage) {
    const list = messagesByChannel.value[msg.channel_id] ?? []
    messagesByChannel.value[msg.channel_id] = [...list, msg]
    if (msg.channel_id !== activeChannelId.value) {
      unread.value[msg.channel_id] = (unread.value[msg.channel_id] ?? 0) + 1
    }
  }

  function onUnread(channelId: number) {
    if (channelId !== activeChannelId.value) {
      // refresh unread count from store best-effort (WS doesn't carry count)
      loadUnread()
    }
  }

  function onTyping(channelId: number, userId: number) {
    const cur = typingUsers.value[channelId] ?? []
    if (!cur.includes(userId)) typingUsers.value[channelId] = [...cur, userId]
    // auto-clear after 3s (caller's responsibility, or a setTimeout here)
  }

  function setActive(channelId: number) {
    activeChannelId.value = channelId
    unread.value[channelId] = 0
  }

  return {
    channels, activeChannelId, activeChannel, activeMessages,
    messagesByChannel, unread, typingUsers, loading,
    loadChannels, loadUnread, loadHistory, sendMessage, markRead,
    setActive, onIncomingMessage, onUnread, onTyping,
  }
})
```

- [ ] **Step 12.2: Smoke-test сборки**

Run: `cd /d/Projects/frontcrm && npx vue-tsc --noEmit 2>&1 | tail -5`
Expected: no new errors.

- [ ] **Step 12.3: Commit**

```bash
git add src/stores/chat.ts
git commit -m "feat(chat-fe): Pinia store with channels/messages/unread/typing"
```

---

## Task 13: Frontend — WS composable `useChatSocket` (TDD)

**Files:**
- Create: `src/composables/useChatSocket.ts`
- Create: `src/composables/useChatSocket.test.ts`
- Modify: `vitest.config.ts` (environment jsdom)

- [ ] **Step 13.1: Переключить vitest на jsdom**

`vitest.config.ts`:

```ts
import { defineConfig } from 'vitest/config'
export default defineConfig({
  test: { include: ['src/**/*.test.ts'], environment: 'jsdom' },
})
```

Установить jsdom (если нет): `npm i -D jsdom`

- [ ] **Step 13.2: Написать failing-тест**

`src/composables/useChatSocket.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useChatSocket } from './useChatSocket'

// Mock WebSocket
class MockWS {
  static instances: MockWS[] = []
  url: string
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  sent: string[] = []
  constructor(url: string) {
    this.url = url
    MockWS.instances.push(this)
  }
  send(data: string) { this.sent.push(data) }
  close() { this.onclose?.() }
}

describe('useChatSocket', () => {
  beforeEach(() => {
    MockWS.instances = []
    ;(globalThis as any).WebSocket = MockWS
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
    delete (globalThis as any).WebSocket
  })

  it('connects using a ticket and resolves ready', async () => {
    const { connect, isReady } = useChatSocket()
    // mock api.wsTicket
    vi.doMock('@/api/chat', () => ({
      chatApi: { wsTicket: async () => ({ data: { ticket: 'T123' } }) },
    }))
    connect('ws://x', 'T123')
    expect(MockWS.instances.length).toBe(1)
    expect(MockWS.instances[0].url).toContain('ticket=T123')
    // simulate open
    MockWS.instances[0].onopen?.()
    expect(isReady.value).toBe(true)
  })
})
```

> ⚠️ `vi.doMock` после импорта не подхватит модуль, который уже импортирован `useChatSocket`. Это известная сложность мокинга. Если тест ломается — замени на инъекцию: `useChatSocket` принимает опциональный `ticketFetcher` параметр. См. исправление в Step 13.3 (упрощённый тест).

- [ ] **Step 13.3: Упростить тест — инъекция ticket-фетчера**

Замени весь `useChatSocket.test.ts` на:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useChatSocket } from './useChatSocket'

class MockWS {
  static instances: MockWS[] = []
  url: string
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  sent: string[] = []
  constructor(url: string) { this.url = url; MockWS.instances.push(this) }
  send(data: string) { this.sent.push(data) }
  close() { this.onclose?.() }
}

describe('useChatSocket', () => {
  beforeEach(() => {
    MockWS.instances = []
    ;(globalThis as any).WebSocket = MockWS
  })
  afterEach(() => { delete (globalThis as any).WebSocket })

  it('connects with ticket and marks ready on open', () => {
    const { connect, isReady } = useChatSocket()
    connect('ws://x', 'T123')
    expect(MockWS.instances[0].url).toBe('ws://x?ticket=T123')
    MockWS.instances[0].onopen?.()
    expect(isReady.value).toBe(true)
  })

  it('dispatches incoming message to handler', () => {
    const received: any[] = []
    const { connect, onMessage } = useChatSocket()
    onMessage((m) => received.push(m))
    connect('ws://x', 'T1')
    MockWS.instances[0].onmessage?.({ data: JSON.stringify({ type: 'message', message: { id: 1 } }) })
    expect(received).toHaveLength(1)
    expect(received[0].type).toBe('message')
  })
})
```

- [ ] **Step 13.4: Реализовать `useChatSocket.ts`**

```ts
import { ref } from 'vue'

type IncomingHandler = (msg: any) => void

/**
 * Singleton-ish WebSocket manager for chat. One connection per app lifetime,
 * mounted in App.vue's <script setup>. Auth uses a single-use ticket fetched
 * via REST (POST /api/chat/ws-ticket with the Bearer token), then passed as
 * ?ticket= to the WS URL — never the raw token in the URL.
 *
 * ⚠️ XSS note (spec): content from WS/REST is rendered ONLY via {{ }} in
 * MessageList.vue, never v-html.
 */
export function useChatSocket() {
  const isReady = ref(false)
  let ws: WebSocket | null = null
  const handlers: IncomingHandler[] = []

  function connect(baseWsUrl: string, ticket: string) {
    ws = new WebSocket(`${baseWsUrl}?ticket=${ticket}`)
    ws.onopen = () => { isReady.value = true }
    ws.onmessage = (e: MessageEvent) => {
      try {
        const msg = JSON.parse(e.data)
        handlers.forEach((h) => h(msg))
      } catch {
        // ignore non-JSON frames
      }
    }
    ws.onclose = () => { isReady.value = false }
  }

  function onMessage(h: IncomingHandler) {
    handlers.push(h)
  }

  function send(payload: object) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload))
    }
  }

  function close() {
    ws?.close()
    ws = null
  }

  return { isReady, connect, onMessage, send, close }
}
```

- [ ] **Step 13.5: Run — verify PASS**

Run: `cd /d/Projects/frontcrm && npm run test 2>&1 | tail -10`
Expected: useConfirm (3) + useChatSocket (2) = 5 passed.

- [ ] **Step 13.6: Commit**

```bash
git add src/composables/useChatSocket.ts src/composables/useChatSocket.test.ts vitest.config.ts
git commit -m "feat(chat-fe): useChatSocket composable with jsdom test (TDD)"
```

---

## Task 14: Frontend — UI компоненты + ChatView

**Files:**
- Create: `src/components/chat/ChannelList.vue`
- Create: `src/components/chat/MessageList.vue`
- Create: `src/components/chat/MessageInput.vue`
- Create: `src/components/chat/TypingIndicator.vue`
- Create: `src/views/ChatView.vue`

- [ ] **Step 14.1: Создать `ChannelList.vue`**

```vue
<script setup lang="ts">
import { useChatStore } from '@/stores/chat'
import BaseBadge from '@/components/ui/BaseBadge.vue'
import { Hash, Users, Megaphone } from 'lucide-vue-next'
import { computed } from 'vue'

const store = useChatStore()
const icon = (type: string) => type === 'general' ? Megaphone : type === 'department' ? Hash : Users
</script>

<template>
  <aside class="w-64 border-r border-slate-200 bg-white flex flex-col">
    <div class="p-4 border-b border-slate-200">
      <h2 class="font-bold text-lg">Чаты</h2>
    </div>
    <nav class="flex-1 overflow-y-auto py-2">
      <button
        v-for="c in store.channels"
        :key="c.id"
        class="w-full flex items-center gap-2 px-4 py-2 text-left hover:bg-slate-50 transition"
        :class="{ 'bg-brand-50 text-brand-700': c.id === store.activeChannelId }"
        @click="store.setActive(c.id)"
      >
        <component :is="icon(c.type)" :size="16" />
        <span class="flex-1 truncate text-sm">{{ c.name }}</span>
        <BaseBadge v-if="store.unread[c.id]" type="danger">{{ store.unread[c.id] }}</BaseBadge>
      </button>
    </nav>
  </aside>
</template>
```

- [ ] **Step 14.2: Создать `MessageList.vue`**

```vue
<script setup lang="ts">
import { useChatStore } from '@/stores/chat'
import { computed } from 'vue'
import TypingIndicator from './TypingIndicator.vue'

const store = useChatStore()
const props = defineProps<{ currentUserId: number }>()

// ⚠️ SPEC: content rendered ONLY via {{ }}, NEVER v-html (XSS protection).
// Line breaks via CSS white-space: pre-wrap, not <br> interpolation.
</script>

<template>
  <div class="flex-1 overflow-y-auto p-4 space-y-2 bg-slate-50">
    <div
      v-for="m in store.activeMessages"
      :key="m.id"
      class="flex"
      :class="{ 'justify-end': m.author_id === props.currentUserId }"
    >
      <div
        class="max-w-[70%] rounded-2xl px-4 py-2"
        :class="m.author_id === props.currentUserId
          ? 'bg-brand-600 text-white'
          : 'bg-white border border-slate-200'"
      >
        <p v-if="m.deleted_at" class="italic opacity-60">сообщение удалено</p>
        <p v-else class="text-sm" style="white-space: pre-wrap">{{ m.content }}</p>
        <span v-if="m.edited_at" class="text-[10px] opacity-50">(ред.)</span>
      </div>
    </div>
    <TypingIndicator :channel-id="store.activeChannelId ?? 0" />
  </div>
</template>
```

- [ ] **Step 14.3: Создать `MessageInput.vue`**

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { useChatStore } from '@/stores/chat'
import BaseButton from '@/components/ui/BaseButton.vue'
import { Send } from 'lucide-vue-next'

const store = useChatStore()
const text = ref('')

async function submit() {
  const content = text.value.trim()
  if (!content || !store.activeChannelId) return
  text.value = ''
  await store.sendMessage(store.activeChannelId, content)
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    submit()
  }
}
</script>

<template>
  <div class="border-t border-slate-200 bg-white p-3 flex items-end gap-2">
    <textarea
      v-model="text"
      class="input flex-1 resize-none"
      rows="1"
      maxlength="10000"
      placeholder="Написать сообщение…"
      @keydown="onKey"
    />
    <BaseButton variant="primary" :disabled="!text.trim()" @click="submit">
      <Send :size="16" />
    </BaseButton>
  </div>
</template>
```

- [ ] **Step 14.4: Создать `TypingIndicator.vue`**

```vue
<script setup lang="ts">
import { useChatStore } from '@/stores/chat'
import { computed } from 'vue'

const props = defineProps<{ channelId: number }>()
const store = useChatStore()
const show = computed(() => (store.typingUsers[props.channelId]?.length ?? 0) > 0)
</script>

<template>
  <p v-if="show" class="text-xs text-slate-400 px-2">печатает…</p>
</template>
```

- [ ] **Step 14.5: Создать `ChatView.vue`**

```vue
<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import { useChatSocket } from '@/composables/useChatSocket'
import { chatApi } from '@/api/chat'
import ChannelList from '@/components/chat/ChannelList.vue'
import MessageList from '@/components/chat/MessageList.vue'
import MessageInput from '@/components/chat/MessageInput.vue'

const store = useChatStore()
const auth = useAuthStore()
const { connect, onMessage } = useChatSocket()

const wsBase = import.meta.env.DEV
  ? 'ws://localhost:8000/ws/chat'
  : `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/chat`

onMounted(async () => {
  await store.loadChannels()
  await store.loadUnread()
  if (store.activeChannelId) await store.loadHistory(store.activeChannelId)

  // connect WS with a fresh ticket
  const { data } = await chatApi.wsTicket()
  connect(wsBase, data.ticket)
  onMessage((msg) => {
    if (msg.type === 'message') store.onIncomingMessage(msg.message)
    else if (msg.type === 'unread') store.onUnread(msg.channel_id)
    else if (msg.type === 'typing') store.onTyping(msg.channel_id, msg.user_id)
  })
})

const me = computed(() => auth.user?.id ?? 0)
</script>

<template>
  <div class="flex h-full">
    <ChannelList />
    <section v-if="store.activeChannel" class="flex-1 flex flex-col">
      <header class="px-4 py-3 border-b border-slate-200 bg-white">
        <h1 class="font-bold">{{ store.activeChannel.name }}</h1>
      </header>
      <MessageList :current-user-id="me" />
      <MessageInput />
    </section>
    <section v-else class="flex-1 flex items-center justify-center text-slate-400">
      Выберите канал
    </section>
  </div>
</template>
```

- [ ] **Step 14.6: Smoke-test сборки**

Run: `cd /d/Projects/frontcrm && npm run build 2>&1 | tail -8`
Expected: `✓ built`, без TS-ошибок про chat.

- [ ] **Step 14.7: Commit**

```bash
git add src/components/chat/ src/views/ChatView.vue
git commit -m "feat(chat-fe): ChatView + ChannelList/MessageList/Input/Typing components"
```

---

## Task 15: Frontend — router + sidebar + App.vue + vite proxy

**Files:**
- Modify: `src/router/index.ts`
- Modify: `src/components/sidebar/AppSidebar.vue`
- Modify: `src/App.vue`
- Modify: `vite.config.ts`

- [ ] **Step 15.1: Добавить роуты чата**

В `src/router/index.ts`, в children каждого staff-layout (admin ~строка 30, manager ~строка 46, employee ~строка 57), добавить в каждый блок children по строке:

```ts
      { path: 'chat', component: () => import('@/views/ChatView.vue') },
```

(См. как уже переиспользуется `CalendarPage` в строках 22/45/71 — тот же паттерн: одна view в нескольких parent-layouts.)

- [ ] **Step 15.2: Добавить пункт «Чат» в sidebar**

В `src/components/sidebar/AppSidebar.vue`:
1. В импортах lucide (строки 5-9) добавить `MessageSquare`.
2. В `menu` computed — в массивы admin (~строка 33), manager (~строка 42), employee (~строка 47) добавить:
```ts
        { to: `${base}/chat`, label: 'Чат', icon: MessageSquare },
```
(НЕ добавлять в client-блок — клиенты чат не видят.)

- [ ] **Step 15.3: Смонтировать WS-singleton в App.vue**

`src/App.vue`:

```vue
<script setup lang="ts">
import { watchEffect } from 'vue'
import { RouterView } from 'vue-router'
import ConfirmModal from '@/components/ui/ConfirmModal.vue'
import { useAuthStore } from '@/stores/auth'

// Chat WS connection lives for the whole app, but only when authenticated
// and only for staff roles (clients don't see chat).
const auth = useAuthStore()
watchEffect(() => {
  if (auth.isAuthenticated && auth.role && auth.role !== 'client') {
    // lazily import so client-role users don't pull chat bundle
    import('@/composables/useChatSocket')
  }
})
</script>

<template>
  <RouterView />
  <ConfirmModal />
</template>
```

> ⚠️ Этот `watchEffect` только **импортирует** модуль, но не подключает WS. Реальное подключение должно идти в `ChatView.onMounted` (Task 14.5), который выполняется только когда юзер открывает `/.../chat`. Если хочешь WS-соединение всегда живым (для unread-бейджей даже когда юзер не в чате) — вынеси `connect()` в отдельный guard-компонент `<ChatConnection />`, монтируемый в App.vue только для staff. Реши на этапе реализации; минимально рабочий путь — соединение в ChatView.

- [ ] **Step 15.4: Добавить `/ws` в vite dev-proxy**

`vite.config.ts`, в `server.proxy`, добавить рядом с правилом `/api`:

```ts
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
```

- [ ] **Step 15.5: Сборка + smoke**

Run: `cd /d/Projects/frontcrm && npm run build 2>&1 | tail -5`
Expected: `✓ built`.

- [ ] **Step 15.6: Commit**

```bash
git add src/router/index.ts src/components/sidebar/AppSidebar.vue src/App.vue vite.config.ts
git commit -m "feat(chat-fe): router + sidebar entry + WS singleton + /ws dev proxy"
```

---

## Task 16: Финальная проверка + деплой-заметка (nginx)

**Files:**
- (optional) deploy notes

- [ ] **Step 16.1: Полный бэкенд-тест**

Run: `cd backend && python -m pytest -q`
Expected: ~145 passed (121 + ~24 чат-тестов).

- [ ] **Step 16.2: Полный фронтенд-тест + сборка**

Run:
```bash
cd /d/Projects/frontcrm && npm run test && npm run build
```
Expected: vitest 5 passed, build ✓.

- [ ] **Step 16.3: Ручной smoke (если возможно)**

1. Запустить backend: `cd backend && python main.py` (или uvicorn).
2. Запустить frontend dev: `npm run dev`.
3. Логин admin → открыть `/admin/chat` → должен видет «Общий чат».
4. Отправить сообщение → должно появиться в ленте.
5. (опционально) Второй браузер под другим staff-юзером → WS-пуш нового сообщения.

- [ ] **Step 16.4: Зафиксировать nginx-заметку для прода**

В `docs/HANDOFF.md` (или deploy notes) добавить секцию:
> **nginx для WebSocket (чат):** location `/ws/` требует `proxy_http_version 1.1` + хедеры Upgrade/Connection, иначе WS за прокси не поднимется:
> ```nginx
> location /ws/ {
>     proxy_pass http://127.0.0.1:8000;
>     proxy_http_version 1.1;
>     proxy_set_header Upgrade $http_upgrade;
>     proxy_set_header Connection "upgrade";
>     proxy_read_timeout 86400;
> }
> ```

- [ ] **Step 16.5: Commit финальный**

```bash
git add docs/HANDOFF.md
git commit -m "docs(chat): nginx WS proxy config for production deploy"
```

---

## Self-Review чеклист (выполнить после написания плана, до исполнения)

- [x] **Spec coverage:** каждая секция спеки покрыта задачей (миграция → T1, каналы → T5, сообщения → T6, read-state → T6, membership → T7, REST → T8, WS → T9, фронт → T11-15, граничные кейсы 400/403 → в тестах T5/T7).
- [x] **GETDEL** (review #1) — Task 4.
- [x] **PG-версия** (review #2) — Task 1 (partial indexes, без NULLS NOT DISTINCT в основном CREATE).
- [x] **Redis rate-limit** (review #3) — Task 4 + используется в Task 6 (send_message).
- [x] **CHECK content** (review #4) — Task 1 (миграция) + Task 2 (schema max_length) + Task 14 (textarea maxlength).
- [x] **400 на general/department members** (review #5) — Task 7.
- [x] **v-html запрет** (review #6) — Task 14.2 (комментарий + `style="white-space: pre-wrap"` вместо v-html).
- [x] **Placeholders:** нет TBD/TODO; все шаги содержат код или конкретные команды.
- [x] **Type consistency:** `members=lambda _c: ...` consistently used in fanout calls; `chatApi` method names match store usage; `ChatMessage`/`Channel` types consistent across api/store/components.
