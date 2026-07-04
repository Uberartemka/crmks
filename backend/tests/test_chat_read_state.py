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

    # NOTE: tests run where Redis may be down; stub the rate limiter that
    # send_message imports locally so the read-state logic under test is not
    # masked by a Redis ConnectionError. Remove to exercise real limiter.
    import services.chat_redis as chat_redis_mod
    monkeypatch.setattr(chat_redis_mod, "allow_message", lambda _uid: True)


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
