"""Tests for machinery CRUD + owner-check + client_id binding."""
import asyncio
import os

import psycopg2
import pytest
from fastapi import HTTPException

from services.machinery_service import (
    create_machinery,
    delete_machinery,
    list_machinery,
    update_machinery,
)
from schemas.machinery import MachineryCreate, MachineryUpdate


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def seeded_machinery(db_conn, monkeypatch):
    """Seed clients/users/machinery tables; patch get_db to return the test conn."""
    import services.machinery_service as svc

    cur = db_conn.cursor()
    cur.execute("DROP TABLE IF EXISTS machinery CASCADE")
    cur.execute("DROP TABLE IF EXISTS clients CASCADE")
    cur.execute("DROP TABLE IF EXISTS users CASCADE")
    cur.execute("CREATE TABLE clients (id SERIAL PRIMARY KEY, name TEXT)")
    cur.execute(
        "CREATE TABLE users (id SERIAL PRIMARY KEY, username TEXT, role TEXT, client_id INTEGER)"
    )
    cur.execute(
        """CREATE TABLE machinery (
        id SERIAL PRIMARY KEY, client_id INTEGER, created_by INTEGER,
        name TEXT NOT NULL, node TEXT, bearing TEXT, brand TEXT,
        install_date TEXT, wear INTEGER DEFAULT 0, status TEXT DEFAULT 'normal',
        created_at TEXT, updated_at TEXT)"""
    )
    cur.execute("INSERT INTO clients (name) VALUES ('ООО Ромашка'), ('ООО Вектор')")
    cur.execute(
        "INSERT INTO users (username, role, client_id) VALUES ('client1','client',1), ('admin','admin',NULL)"
    )
    cur.close()

    TEST_DSN = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://postgres:235813@localhost:5432/hhb_b2b_test",
    )

    def _test_get_db():
        return psycopg2.connect(TEST_DSN)

    monkeypatch.setattr(svc, "get_db", _test_get_db)


def test_create_machinery_as_client_binds_own_client_id(seeded_machinery):
    d = _run(
        create_machinery(
            data=MachineryCreate(name="Нория №1"),
            current_user={"id": 1, "role": "client", "client_id": 1},
        )
    )
    assert d["client_id"] == 1
    assert d["created_by"] == 1


def test_list_machinery_client_sees_only_own(seeded_machinery):
    _run(
        create_machinery(
            data=MachineryCreate(name="A"),
            current_user={"id": 1, "role": "client", "client_id": 1},
        )
    )
    _run(
        create_machinery(
            data=MachineryCreate(name="B", client_id=2),
            current_user={"id": 2, "role": "admin"},
        )
    )
    mine = _run(list_machinery(current_user={"id": 1, "role": "client", "client_id": 1}))
    assert len(mine) == 1
    assert mine[0]["name"] == "A"


def test_list_machinery_admin_sees_all(seeded_machinery):
    _run(
        create_machinery(
            data=MachineryCreate(name="A"),
            current_user={"id": 1, "role": "client", "client_id": 1},
        )
    )
    _run(
        create_machinery(
            data=MachineryCreate(name="B", client_id=2),
            current_user={"id": 2, "role": "admin"},
        )
    )
    all_d = _run(list_machinery(current_user={"id": 2, "role": "admin"}))
    assert len(all_d) >= 2


def test_update_machinery_owner_check(seeded_machinery):
    d = _run(
        create_machinery(
            data=MachineryCreate(name="X"),
            current_user={"id": 1, "role": "client", "client_id": 1},
        )
    )
    with pytest.raises(HTTPException) as exc:
        _run(
            update_machinery(
                machinery_id=d["id"],
                data=MachineryUpdate(status="critical"),
                current_user={"id": 99, "role": "client", "client_id": 2},
            )
        )
    assert exc.value.status_code == 403


def test_delete_machinery_owner_check(seeded_machinery):
    d = _run(
        create_machinery(
            data=MachineryCreate(name="X"),
            current_user={"id": 1, "role": "client", "client_id": 1},
        )
    )
    with pytest.raises(HTTPException) as exc:
        _run(
            delete_machinery(
                machinery_id=d["id"],
                current_user={"id": 99, "role": "client", "client_id": 2},
            )
        )
    assert exc.value.status_code == 403
