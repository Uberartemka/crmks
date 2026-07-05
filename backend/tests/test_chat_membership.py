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
    cur.execute("CREATE TABLE users (id SERIAL PRIMARY KEY, username TEXT, role TEXT, name TEXT, avatar_file_id BIGINT NULL)")
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
    cur.execute("INSERT INTO users (username,role,name) VALUES ('a','admin','Админ'),('b','manager','Менеджер'),('c','employee','Сотрудник')")
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


# ---- list_members / list_staff_users (channel-info panel + invite dropdown) ----

from services.chat_service import list_members, list_staff_users


def test_list_members_general_returns_all_staff(seeded_mem):
    members = _run(list_members(channel_id=1, current_user={"id": 1, "role": "admin"}))
    ids = {m["id"] for m in members}
    assert ids == {1, 2, 3}  # general = all staff
    # each member carries name for display
    assert all("name" in m and m["name"] for m in members)


def test_list_members_department_filters_by_role(seeded_mem):
    members = _run(list_members(channel_id=2, current_user={"id": 2, "role": "manager"}))
    ids = {m["id"] for m in members}
    assert ids == {2}  # department 'manager' → only the manager


def test_list_members_topic_returns_only_explicit_members(seeded_mem):
    # channel 3 is a topic where only user 1 is a member (seeded)
    members = _run(list_members(channel_id=3, current_user={"id": 1, "role": "admin"}))
    ids = {m["id"] for m in members}
    assert ids == {1}


def test_list_staff_users_returns_only_staff(db_conn, seeded_mem):
    # add a client user to confirm it's excluded
    cur = db_conn.cursor()
    cur.execute("INSERT INTO users (username,role,name) VALUES ('cl','client','Клиент')")
    cur.close()
    users = _run(list_staff_users(current_user={"id": 1, "role": "admin"}))
    usernames = {u["username"] for u in users}
    assert "cl" not in usernames  # client excluded
    assert {"a", "b", "c"}.issubset(usernames)  # staff included
