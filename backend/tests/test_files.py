"""Tests for file service: validation, upload, download, owner-check, security."""
import asyncio
import os

import psycopg2
import pytest
from fastapi import HTTPException

from services.file_service import is_allowed, sanitize_name, save_upload, get_file


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


def test_save_upload_mime_ext_mismatch_415(seeded_files):
    # Real ZIP magic bytes, but filename claims .pdf → mismatch → 415
    zip_bytes = b"PK\x03\x04\x14\x00\x00\x00\x08\x00" + b"\x00" * 20 + b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00test"
    upload = _make_upload(zip_bytes, "report.pdf", "application/pdf")
    with pytest.raises(HTTPException) as exc:
        _run(save_upload(upload=upload, current_user={"id": 1, "role": "manager"}))
    assert exc.value.status_code == 415
    # temp file cleaned up after rejection
    leftover = [f for f in os.listdir(seeded_files) if f.endswith(".part")]
    assert leftover == []


def test_save_upload_image_generates_thumbnail(seeded_files):
    # Minimal valid 1x1 PNG (Pillow-decodable so thumbnail generation succeeds)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
        b"\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    upload = _make_upload(png_bytes, "avatar.png", "image/png")
    meta = _run(save_upload(upload=upload, current_user={"id": 1, "role": "manager"}))
    assert meta["is_image"] is True
    assert meta["thumbnail_url"] is not None
    # thumbnail file physically exists
    assert os.path.exists(os.path.join(seeded_files, meta["_storage_path"].rsplit(".", 1)[0] + "_thumb.jpg"))


def _seed_one_file(seeded_files, owner_id=1):
    """Upload a PDF as owner_id, return its metadata."""
    pdf_bytes = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\nxref\n0 3\ntrailer<</Size 3/Root 1 0 R>>\nstartxref\n0\n%%EOF"
    upload = _make_upload(pdf_bytes, "doc.pdf", "application/pdf")
    return _run(save_upload(upload=upload, current_user={"id": owner_id, "role": "manager"}))


def test_get_file_owner_200(seeded_files):
    meta = _seed_one_file(seeded_files, owner_id=1)
    row, abs_path = get_file(file_id=meta["id"], current_user={"id": 1, "role": "manager"})
    assert row["id"] == meta["id"]
    assert row["mime_type"] == "application/pdf"
    assert os.path.exists(abs_path)


def test_get_file_non_owner_403(seeded_files):
    meta = _seed_one_file(seeded_files, owner_id=1)
    with pytest.raises(HTTPException) as exc:
        get_file(file_id=meta["id"], current_user={"id": 2, "role": "manager"})
    assert exc.value.status_code == 403


def test_get_file_admin_200_on_others_file(seeded_files):
    meta = _seed_one_file(seeded_files, owner_id=1)
    row, abs_path = get_file(file_id=meta["id"], current_user={"id": 3, "role": "admin"})
    assert row["id"] == meta["id"]


def test_get_nonexistent_file_404(seeded_files):
    with pytest.raises(HTTPException) as exc:
        get_file(file_id=999999, current_user={"id": 1, "role": "manager"})
    assert exc.value.status_code == 404
