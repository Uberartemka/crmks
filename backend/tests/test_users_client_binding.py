"""Tests for /api/users client_id binding (Group C activation).

Verifies that POST /api/users can bind a client-role user to a company,
and that GET /api/users returns client_id + client_name via LEFT JOIN.
"""
import os

import psycopg2
import pytest
from fastapi import HTTPException

from schemas.auth import UserCreate


@pytest.fixture
def seeded_users(db_conn, monkeypatch):
    """Create minimal clients/users tables, patch get_db in routes.index."""
    import routes.index as idx
    import utils.db_utils as db_utils

    cur = db_conn.cursor()
    # Ensure users table has client_id column (migration 005 shape).
    cur.execute("DROP TABLE IF EXISTS users CASCADE")
    cur.execute("DROP TABLE IF EXISTS clients CASCADE")
    cur.execute("CREATE TABLE clients (id SERIAL PRIMARY KEY, name TEXT)")
    cur.execute(
        """CREATE TABLE users (
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE,
        password_hash TEXT,
        name TEXT,
        role TEXT DEFAULT 'employee',
        client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
        created_at TEXT)"""
    )
    cur.execute("INSERT INTO clients (name) VALUES ('ООО Ромашка'), ('ООО Вектор')")
    cur.close()

    TEST_DSN = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://postgres:235813@localhost:5432/hhb_b2b_test",
    )

    def _test_get_db():
        return psycopg2.connect(TEST_DSN)

    monkeypatch.setattr(idx, "get_db", _test_get_db)
    monkeypatch.setattr(db_utils, "_use_pg", True)
    return idx


def _admin() -> dict:
    return {"id": 1, "username": "admin", "name": "Admin", "role": "admin", "client_id": None}


def test_create_client_user_binds_client_id(seeded_users):
    idx = seeded_users
    out = idx.create_user(
        data=UserCreate(
            username="buyer1",
            password="secret123",
            name="Закупщик Ромашка",
            role="client",
            client_id=1,
        ),
        current_user=_admin(),
    )
    assert out["client_id"] == 1
    assert out["client_name"] == "ООО Ромашка"
    assert out["role"] == "client"


def test_create_client_user_without_client_id_is_400(seeded_users):
    idx = seeded_users
    with pytest.raises(HTTPException) as exc:
        idx.create_user(
            data=UserCreate(
                username="buyer2",
                password="secret123",
                name="Без компании",
                role="client",
            ),
            current_user=_admin(),
        )
    assert exc.value.status_code == 400
    assert "компани" in exc.value.detail.lower()


def test_create_client_user_with_unknown_client_id_is_400(seeded_users):
    idx = seeded_users
    with pytest.raises(HTTPException) as exc:
        idx.create_user(
            data=UserCreate(
                username="buyer3",
                password="secret123",
                name="Несуществующая компания",
                role="client",
                client_id=9999,
            ),
            current_user=_admin(),
        )
    assert exc.value.status_code == 400


def test_list_users_returns_client_name(seeded_users):
    idx = seeded_users
    # create a client user bound to client 2 and a plain admin
    idx.create_user(
        data=UserCreate(
            username="buyer4",
            password="x",
            name="Закупщик Вектор",
            role="client",
            client_id=2,
        ),
        current_user=_admin(),
    )
    users = idx.list_users(current_user=_admin())
    bound = next(u for u in users if u["username"] == "buyer4")
    assert bound["client_id"] == 2
    assert bound["client_name"] == "ООО Вектор"
    # admin record (id=1 is not in this fresh table) — just ensure no crash on NULL
    assert all("client_name" in u for u in users)


def test_list_users_admin_without_binding_shows_null(seeded_users):
    idx = seeded_users
    idx.create_user(
        data=UserCreate(
            username="manager1",
            password="x",
            name="Менеджер",
            role="manager",
        ),
        current_user=_admin(),
    )
    users = idx.list_users(current_user=_admin())
    mgr = next(u for u in users if u["username"] == "manager1")
    assert mgr["client_id"] is None
    assert mgr["client_name"] is None
