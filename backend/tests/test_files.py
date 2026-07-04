"""Tests for file service: validation, upload, download, owner-check, security."""
import asyncio
import os

import psycopg2
import pytest
from fastapi import HTTPException

from services.file_service import is_allowed, sanitize_name


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def seeded_files(db_conn, monkeypatch):
    """Seed users + files tables; patch get_db to return the test conn."""
    import services.file_service as svc

    cur = db_conn.cursor()
    cur.execute("DROP TABLE IF EXISTS files CASCADE")
    cur.execute("DROP TABLE IF EXISTS users CASCADE")
    cur.execute(
        "CREATE TABLE users (id SERIAL PRIMARY KEY, username TEXT, role TEXT, name TEXT)"
    )
    cur.execute(
        """CREATE TABLE files (
        id BIGSERIAL PRIMARY KEY, uploaded_by INTEGER,
        storage_path TEXT NOT NULL, thumbnail_path TEXT NULL,
        original_name TEXT NOT NULL, mime_type TEXT NOT NULL,
        size_bytes BIGINT NOT NULL, sha256 TEXT NOT NULL,
        is_image BOOLEAN NOT NULL DEFAULT false,
        created_at TIMESTAMPTZ DEFAULT now())"""
    )
    cur.execute(
        "INSERT INTO users (username, role, name) VALUES "
        "('alice', 'manager', 'Алиса'), ('bob', 'manager', 'Боб'), ('admin', 'admin', 'Админ')"
    )
    cur.close()

    TEST_DSN = os.environ.get(
        "TEST_DATABASE_URL", "postgresql://postgres:235813@localhost:5432/hhb_b2b_test"
    )

    def _test_get_db():
        return psycopg2.connect(TEST_DSN)

    monkeypatch.setattr(svc, "get_db", _test_get_db)
    # MEDIA_ROOT for tests — a tmp dir inside the test working dir
    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="crmks_media_test_")
    monkeypatch.setattr(svc, "MEDIA_ROOT", tmpdir)
    yield tmpdir


def test_is_allowed_accepts_pdf_with_pdf_ext(seeded_files):
    assert is_allowed("application/pdf", ".pdf") is True


def test_is_allowed_rejects_exe(seeded_files):
    assert is_allowed("application/x-msdownload", ".exe") is False


def test_is_allowed_rejects_mime_ext_mismatch(seeded_files):
    # name says .pdf, but magic detected zip content → mismatch → reject
    assert is_allowed("application/zip", ".pdf") is False


def test_sanitize_name_strips_quotes_and_control(seeded_files):
    # double-quote, CR, LF must be stripped (header injection defense)
    assert sanitize_name('test".pdf') == "test.pdf"
    assert sanitize_name("test\r\nX-Evil: 1.pdf") == "testX-Evil: 1.pdf"
    # empty after sanitize → fallback
    assert sanitize_name('""') == "file"
