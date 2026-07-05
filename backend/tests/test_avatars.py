"""Tests for user avatars: avatar_url in me/list_users, PATCH endpoint."""
import asyncio
import os

import psycopg2
import pytest
from fastapi import HTTPException

from routes.index import _avatar_url  # helper added in Step 4 below


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def seeded_avatars(db_conn, monkeypatch):
    """Seed users + files; patch get_db in routes.index and chat_service."""
    import routes.index as idx
    import services.chat_service as svc

    cur = db_conn.cursor()
    cur.execute("DROP TABLE IF EXISTS messages CASCADE")
    cur.execute("DROP TABLE IF EXISTS channels CASCADE")
    cur.execute("DROP TABLE IF EXISTS channel_members CASCADE")
    cur.execute("DROP TABLE IF EXISTS files CASCADE")
    cur.execute("DROP TABLE IF EXISTS users CASCADE")
    cur.execute(
        "CREATE TABLE users (id SERIAL PRIMARY KEY, username TEXT, password_hash TEXT, "
        "name TEXT, role TEXT, client_id INTEGER, avatar_file_id BIGINT NULL, created_at TEXT)"
    )
    cur.execute(
        "CREATE TABLE files (id BIGSERIAL PRIMARY KEY, uploaded_by INTEGER, storage_path TEXT, "
        "thumbnail_path TEXT, original_name TEXT, mime_type TEXT, size_bytes BIGINT, "
        "sha256 TEXT, is_image BOOLEAN DEFAULT false, created_at TIMESTAMPTZ DEFAULT now())"
    )
    cur.execute(
        "INSERT INTO users (username, password_hash, name, role) VALUES "
        "('alice', 'x', 'Алиса', 'manager'), ('bob', 'x', 'Боб', 'manager')"
    )
    cur.execute(
        "INSERT INTO files (uploaded_by, storage_path, original_name, mime_type, size_bytes, sha256, is_image) "
        "VALUES (1, '2026/07/a.png', 'ava.png', 'image/png', 100, 'abc', true)"
    )
    cur.execute("UPDATE users SET avatar_file_id = 1 WHERE id = 1")
    cur.close()

    TEST_DSN = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:235813@localhost:5432/hhb_b2b_test")

    def _test_get_db():
        return psycopg2.connect(TEST_DSN)

    monkeypatch.setattr(idx, "get_db", _test_get_db)
    monkeypatch.setattr(svc, "get_db", _test_get_db)


def test_avatar_url_helper():
    assert _avatar_url(1) == "/api/files/1"
    assert _avatar_url(None) is None


def test_me_returns_avatar_url_when_set(seeded_avatars):
    from routes.index import me
    out = me(current_user={"id": 1, "username": "alice", "name": "Алиса", "role": "manager", "client_id": None, "avatar_file_id": 1})
    assert out["avatar_file_id"] == 1
    assert out["avatar_url"] == "/api/files/1"


def test_me_avatar_url_null_when_no_avatar(seeded_avatars):
    from routes.index import me
    out = me(current_user={"id": 2, "username": "bob", "name": "Боб", "role": "manager", "client_id": None, "avatar_file_id": None})
    assert out["avatar_file_id"] is None
    assert out["avatar_url"] is None


def test_update_my_avatar_sets_file_id(seeded_avatars):
    from routes.index import update_my_avatar, AvatarUpdate
    out = update_my_avatar(
        data=AvatarUpdate(file_id=1),
        current_user={"id": 1, "username": "alice", "name": "Алиса", "role": "manager", "client_id": None, "avatar_file_id": None},
    )
    assert out["ok"] is True
    assert out["avatar_file_id"] == 1
    assert out["avatar_url"] == "/api/files/1"
    # DB updated
    conn = psycopg2.connect(os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:235813@localhost:5432/hhb_b2b_test"))
    cur = conn.cursor()
    cur.execute("SELECT avatar_file_id FROM users WHERE id = 1")
    assert cur.fetchone()[0] == 1
    conn.close()


def test_update_my_avatar_other_users_file_403(seeded_avatars):
    from routes.index import update_my_avatar, AvatarUpdate
    # file 1 was uploaded_by=1 (alice); bob (id=2) tries to use it
    with pytest.raises(HTTPException) as exc:
        update_my_avatar(
            data=AvatarUpdate(file_id=1),
            current_user={"id": 2, "username": "bob", "name": "Боб", "role": "manager", "client_id": None, "avatar_file_id": None},
        )
    assert exc.value.status_code == 403
