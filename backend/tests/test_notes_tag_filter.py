"""Tests for list_notes optional tag filter (GET /api/notes?tag=audit)."""
import asyncio
import os

import psycopg2
import pytest

from services.notes_service import list_notes


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def seeded_notes(db_conn, monkeypatch):
    """Seed notes with different tags; patch get_db to return the test conn."""
    import services.notes_service as svc

    cur = db_conn.cursor()
    cur.execute("DROP TABLE IF EXISTS notes CASCADE")
    cur.execute(
        """
        CREATE TABLE notes (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            title VARCHAR(300),
            content TEXT NOT NULL,
            color VARCHAR(20) DEFAULT 'yellow',
            pinned INTEGER DEFAULT 0,
            tags TEXT,
            client_id INTEGER,
            created_at VARCHAR(100),
            updated_at VARCHAR(100)
        )
        """
    )
    cur.execute(
        """
        INSERT INTO notes (user_id, title, content, color, pinned, tags, created_at, updated_at) VALUES
        (1, 'Аудит 1', 'content1', 'yellow', 0, '["audit", "чемоданчик"]', '2026-07-01', '2026-07-01'),
        (1, 'Аудит 2', 'content2', 'yellow', 0, '["audit"]', '2026-07-02', '2026-07-02'),
        (1, 'Обычная заметка', 'content3', 'blue', 0, '[]', '2026-07-03', '2026-07-03')
        """
    )
    cur.close()

    TEST_DSN = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:235813@localhost:5432/hhb_b2b_test")

    def _test_get_db():
        return psycopg2.connect(TEST_DSN)

    monkeypatch.setattr(svc, "get_db", _test_get_db)
    return {"user_id": 1}


def test_list_notes_without_tag_returns_all(seeded_notes):
    notes = _run(list_notes(current_user={"id": 1}))
    assert len(notes) == 3


def test_list_notes_with_audit_tag_returns_only_audit(seeded_notes):
    notes = _run(list_notes(current_user={"id": 1}, tag="audit"))
    assert len(notes) == 2
    titles = [n["title"] for n in notes]
    assert "Аудит 1" in titles
    assert "Аудит 2" in titles
    assert "Обычная заметка" not in titles


def test_list_notes_with_unknown_tag_returns_empty(seeded_notes):
    notes = _run(list_notes(current_user={"id": 1}, tag="nonexistent"))
    assert notes == []
