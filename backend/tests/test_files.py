"""Tests for file service: validation, upload, download, owner-check, security."""
import asyncio
import os

import psycopg2
import pytest
from fastapi import HTTPException

from services.file_service import is_allowed, sanitize_name, save_upload


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


def _make_upload(content: bytes, filename: str, content_type: str):
    """Build a minimal fastapi.UploadFile substitute for tests."""
    from io import BytesIO

    class _FakeUpload:
        def __init__(self, content, filename, content_type):
            self.file = BytesIO(content)
            self.filename = filename
            self.content_type = content_type

        async def read(self, n: int = -1):
            return self.file.read(n) if n != -1 else self.file.read()

    return _FakeUpload(content, filename, content_type)


def test_save_upload_pdf_returns_metadata(seeded_files):
    # Minimal valid PDF header so python-magic detects application/pdf
    pdf_bytes = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\nxref\n0 3\n0000000000 65535 f \ntrailer<</Size 3/Root 1 0 R>>\nstartxref\n0\n%%EOF"
    upload = _make_upload(pdf_bytes, "Договор.pdf", "application/pdf")
    meta = _run(save_upload(upload=upload, current_user={"id": 1, "role": "manager"}))
    assert meta["mime_type"] == "application/pdf"
    assert meta["size_bytes"] == len(pdf_bytes)
    assert meta["is_image"] is False
    assert meta["original_name"] == "Договор.pdf"
    assert meta["id"] is not None
    assert meta["url"] == f"/api/files/{meta['id']}"
    # storage_path follows YYYY/MM/<token>.ext
    assert meta["_storage_path"].count("/") == 2
    assert meta["_storage_path"].endswith(".pdf")
    # physical file exists
    assert os.path.exists(os.path.join(seeded_files, meta["_storage_path"]))


def test_save_upload_exceeds_size_limit_413(seeded_files, monkeypatch):
    # patch MAX_SIZE down to 10 bytes to avoid generating 100MB
    import services.file_service as svc
    monkeypatch.setattr(svc, "MAX_SIZE_BYTES", 10)
    upload = _make_upload(b"x" * 100, "big.pdf", "application/pdf")
    with pytest.raises(HTTPException) as exc:
        _run(save_upload(upload=upload, current_user={"id": 1, "role": "manager"}))
    assert exc.value.status_code == 413
