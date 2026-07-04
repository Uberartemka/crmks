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
    cur.execute("CREATE TABLE users (id SERIAL PRIMARY KEY, username TEXT, role TEXT, name TEXT)")
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
    cur.execute("INSERT INTO users (username,role,name) VALUES ('a','admin','Админ'),('b','manager','Менеджер')")
    cur.close()

    TEST_DSN = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:235813@localhost:5432/hhb_b2b_test")
    monkeypatch.setattr(svc, "get_db", lambda: psycopg2.connect(TEST_DSN))

    # NOTE: tests run where Redis may be down; allow_message would raise
    # ConnectionError and mask the logic under test. Stub the rate limiter
    # (via the chat_redis module the service imports) so send_message's
    # local `from services.chat_redis import allow_message` resolves to this.
    # Counter still increments logically (returns True). Remove this stub to
    # exercise the real Redis limiter.
    import services.chat_redis as chat_redis_mod
    monkeypatch.setattr(chat_redis_mod, "allow_message", lambda _uid: True)


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


def test_list_messages_includes_reply_message(seeded_msgs):
    # send a parent message, then a reply to it
    parent = _run(send_message(
        channel_id=2,
        data=MessageCreate(content="parent text"),
        current_user={"id": 1, "role": "manager"},
    ))
    reply = _run(send_message(
        channel_id=2,
        data=MessageCreate(content="reply text", reply_to_id=parent["id"]),
        current_user={"id": 1, "role": "manager"},
    ))
    assert reply["reply_to_id"] == parent["id"]

    hist = _run(list_messages(channel_id=2, current_user={"id": 1, "role": "manager"}))
    # newest first: [reply, parent]
    assert hist[0]["content"] == "reply text"
    # reply_message must be populated with parent content + author_name
    assert hist[0]["reply_message"] is not None
    assert hist[0]["reply_message"]["id"] == parent["id"]
    assert hist[0]["reply_message"]["content"] == "parent text"
    assert hist[0]["reply_message"]["author_name"] == "Админ"
    # parent message has no reply_message of its own
    assert hist[1]["reply_message"] is None


def test_send_message_with_valid_reply_returns_reply_message(seeded_msgs):
    parent = _run(send_message(
        channel_id=2,
        data=MessageCreate(content="parent"),
        current_user={"id": 1, "role": "manager"},
    ))
    out = _run(send_message(
        channel_id=2,
        data=MessageCreate(content="reply", reply_to_id=parent["id"]),
        current_user={"id": 1, "role": "manager"},
    ))
    assert out["reply_to_id"] == parent["id"]
    # response must include the populated reply_message (no extra request needed)
    assert out["reply_message"] is not None
    assert out["reply_message"]["id"] == parent["id"]
    assert out["reply_message"]["content"] == "parent"


def test_send_message_reply_to_nonexistent_parent_gracefully_drops_reply(seeded_msgs):
    # parent id 999999 does not exist → graceful: send as plain message
    out = _run(send_message(
        channel_id=2,
        data=MessageCreate(content="orphan reply", reply_to_id=999999),
        current_user={"id": 1, "role": "manager"},
    ))
    assert out["reply_to_id"] is None
    assert out["reply_message"] is None
    assert out["content"] == "orphan reply"


def test_send_message_reply_to_deleted_parent_drops_reply(seeded_msgs):
    parent = _run(send_message(
        channel_id=2,
        data=MessageCreate(content="will be deleted"),
        current_user={"id": 1, "role": "manager"},
    ))
    _run(delete_message(message_id=parent["id"], current_user={"id": 1, "role": "manager"}))
    out = _run(send_message(
        channel_id=2,
        data=MessageCreate(content="reply after delete", reply_to_id=parent["id"]),
        current_user={"id": 1, "role": "manager"},
    ))
    # parent is soft-deleted → graceful drop
    assert out["reply_to_id"] is None
    assert out["reply_message"] is None


def test_send_message_reply_to_other_channel_drops_reply(seeded_msgs):
    # parent lives in channel 2 (user 1 is member); reply attempted in channel 1
    # (general) pointing at that parent. Cross-channel reply must be rejected by
    # the channel_id match in the guard → graceful drop.
    parent = _run(send_message(
        channel_id=2,
        data=MessageCreate(content="in topic"),
        current_user={"id": 1, "role": "manager"},
    ))
    out = _run(send_message(
        channel_id=1,  # general channel — different from parent's channel 2
        data=MessageCreate(content="cross-channel reply", reply_to_id=parent["id"]),
        current_user={"id": 1, "role": "manager"},
    ))
    assert out["reply_to_id"] is None
    assert out["reply_message"] is None


def test_list_messages_reply_to_deleted_parent_is_null(seeded_msgs):
    parent = _run(send_message(
        channel_id=2,
        data=MessageCreate(content="parent"),
        current_user={"id": 1, "role": "manager"},
    ))
    _run(send_message(
        channel_id=2,
        data=MessageCreate(content="reply", reply_to_id=parent["id"]),
        current_user={"id": 1, "role": "manager"},
    ))
    # now soft-delete the parent
    _run(delete_message(message_id=parent["id"], current_user={"id": 1, "role": "manager"}))
    hist = _run(list_messages(channel_id=2, current_user={"id": 1, "role": "manager"}))
    # find the reply (the non-deleted message)
    reply = next(m for m in hist if m["content"] == "reply")
    # reply_to_id still set in DB, but reply_message is null (parent deleted)
    assert reply["reply_to_id"] == parent["id"]
    assert reply["reply_message"] is None
