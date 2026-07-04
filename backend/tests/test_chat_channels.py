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
