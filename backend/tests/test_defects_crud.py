"""Tests for defects CRUD + owner-check + client_id binding."""
import asyncio
import os

import psycopg2
import pytest
from fastapi import HTTPException

from services.defects_service import (
    create_defect,
    delete_defect,
    list_defects,
    update_defect,
)
from schemas.defects import DefectCreate, DefectUpdate


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def seeded_defects(db_conn, monkeypatch):
    """Seed clients/users/defects tables; patch get_db to return the test conn."""
    import services.defects_service as svc

    cur = db_conn.cursor()
    cur.execute("DROP TABLE IF EXISTS defects CASCADE")
    cur.execute("DROP TABLE IF EXISTS clients CASCADE")
    cur.execute("DROP TABLE IF EXISTS users CASCADE")
    cur.execute("CREATE TABLE clients (id SERIAL PRIMARY KEY, name TEXT)")
    cur.execute(
        "CREATE TABLE users (id SERIAL PRIMARY KEY, username TEXT, role TEXT, client_id INTEGER)"
    )
    cur.execute(
        """CREATE TABLE defects (
        id SERIAL PRIMARY KEY, client_id INTEGER, created_by INTEGER,
        equipment TEXT NOT NULL, bearing TEXT, description TEXT,
        status TEXT DEFAULT 'new', action TEXT, detected_at TEXT,
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


def test_create_defect_as_client_binds_own_client_id(seeded_defects):
    d = _run(
        create_defect(
            data=DefectCreate(equipment="Нория №1", description="Шум"),
            current_user={"id": 1, "role": "client", "client_id": 1},
        )
    )
    assert d["client_id"] == 1
    assert d["created_by"] == 1


def test_list_defects_client_sees_only_own(seeded_defects):
    _run(
        create_defect(
            data=DefectCreate(equipment="A"),
            current_user={"id": 1, "role": "client", "client_id": 1},
        )
    )
    _run(
        create_defect(
            data=DefectCreate(equipment="B", client_id=2),
            current_user={"id": 2, "role": "admin"},
        )
    )
    mine = _run(list_defects(current_user={"id": 1, "role": "client", "client_id": 1}))
    assert len(mine) == 1
    assert mine[0]["equipment"] == "A"


def test_list_defects_admin_sees_all(seeded_defects):
    _run(
        create_defect(
            data=DefectCreate(equipment="A"),
            current_user={"id": 1, "role": "client", "client_id": 1},
        )
    )
    _run(
        create_defect(
            data=DefectCreate(equipment="B", client_id=2),
            current_user={"id": 2, "role": "admin"},
        )
    )
    all_d = _run(list_defects(current_user={"id": 2, "role": "admin"}))
    assert len(all_d) >= 2


def test_update_defect_owner_check(seeded_defects):
    d = _run(
        create_defect(
            data=DefectCreate(equipment="X"),
            current_user={"id": 1, "role": "client", "client_id": 1},
        )
    )
    with pytest.raises(HTTPException) as exc:
        _run(
            update_defect(
                defect_id=d["id"],
                data=DefectUpdate(status="resolved"),
                current_user={"id": 99, "role": "client", "client_id": 2},
            )
        )
    assert exc.value.status_code == 403


def test_delete_defect_owner_check(seeded_defects):
    d = _run(
        create_defect(
            data=DefectCreate(equipment="X"),
            current_user={"id": 1, "role": "client", "client_id": 1},
        )
    )
    with pytest.raises(HTTPException) as exc:
        _run(
            delete_defect(
                defect_id=d["id"],
                current_user={"id": 99, "role": "client", "client_id": 2},
            )
        )
    assert exc.value.status_code == 403
