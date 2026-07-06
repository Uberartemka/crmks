"""Tests for file service: validation, upload, download, owner-check, security."""
import asyncio
import os

import psycopg2
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

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


def test_storage_path_contains_no_user_input(seeded_files):
    """Regression: storage_path must be server-generated (token_hex), not the
    uploaded filename. Prevents path traversal via crafted filenames."""
    evil_name = "../../../../etc/passwd.pdf"
    pdf_bytes = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<</Type/Catalog>>endobj\nxref\n0 1\ntrailer<</Root 1 0 R>>\nstartxref\n0\n%%EOF"
    upload = _make_upload(pdf_bytes, evil_name, "application/pdf")
    meta = _run(save_upload(upload=upload, current_user={"id": 1, "role": "manager"}))
    sp = meta["_storage_path"]
    # no .., no absolute path, only YYYY/MM/<hex>.pdf
    assert ".." not in sp
    assert not sp.startswith("/")
    parts = sp.split("/")
    assert len(parts) == 3
    assert parts[0].isdigit() and parts[1].isdigit()
    assert parts[2].endswith(".pdf")
    assert "../" not in parts[2] and parts[2].count(".") == 1


def test_content_disposition_sanitized_via_save(seeded_files):
    """Defense-in-depth: even if sanitize missed something, the route uses
    quote() so the header can't break. Here we verify the saved name has no
    quotes/CR/LF after sanitize, which is what the route then quotes."""
    evil_name = 'evil"; injection\r\nX-Bad: 1.pdf'
    pdf_bytes = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<</Type/Catalog>>endobj\nxref\n0 1\ntrailer<</Root 1 0 R>>\nstartxref\n0\n%%EOF"
    upload = _make_upload(pdf_bytes, evil_name, "application/pdf")
    meta = _run(save_upload(upload=upload, current_user={"id": 1, "role": "manager"}))
    name = meta["original_name"]
    # sanitize stripped the dangerous chars
    assert '"' not in name
    assert "\r" not in name and "\n" not in name
    # the route would then quote() this — combined defense
    from urllib.parse import quote
    quoted = quote(name)
    # quoted form is safe to embed in an HTTP header (no raw CR/LF/quotes)
    assert "\r" not in quoted and "\n" not in quoted and '"' not in quoted


# ---------------------------------------------------------------------------
# Task 4: public gated /api/chat-attachments/{id} — service-level tests
# ---------------------------------------------------------------------------


def _seed_messages_table(seeded_files):
    """Create a minimal messages table and attach a file to a live message.
    Returns the file id of the attached file. The seeded_files fixture already
    created a files table (migration 010 shape) with users alice(1)/bob(2)/admin(3).
    We DROP/reCREATE the messages stub (only the columns our gate needs: id,
    attachment_id, deleted_at) — same convention as the chat test fixtures
    (seeded_msgs/seeded_rs), which drop+recreate messages per-test. The physical
    file is also written to MEDIA_ROOT so disk-existence checks pass."""
    import psycopg2, os
    TEST_DSN = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:235813@localhost:5432/hhb_b2b_test")
    conn = psycopg2.connect(TEST_DSN)
    try:
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS messages")
        cur.execute(
            "CREATE TABLE messages (id BIGSERIAL PRIMARY KEY, attachment_id BIGINT NULL, "
            "deleted_at TIMESTAMPTZ NULL)"
        )
        cur.execute(
            "INSERT INTO files (uploaded_by, storage_path, original_name, mime_type, "
            "size_bytes, sha256, is_image, thumbnail_path) VALUES "
            "(1, '2026/07/attached.pdf', 'A.pdf', 'application/pdf', 10, 'h1', false, NULL)"
        )
        conn.commit()
        cur.execute("SELECT id FROM files WHERE original_name = 'A.pdf'")
        live_fid = cur.fetchone()[0]
        # attach to a live (non-deleted) message
        cur.execute("INSERT INTO messages (attachment_id, deleted_at) VALUES (%s, NULL)", (live_fid,))
        conn.commit()
        cur.close()
    finally:
        conn.close()
    # write the physical file so disk-existence checks (in get_file_by_attachment
    # and the route StreamingResponse) succeed. seeded_files == MEDIA_ROOT tmpdir.
    os.makedirs(os.path.join(seeded_files, "2026/07"), exist_ok=True)
    with open(os.path.join(seeded_files, "2026/07/attached.pdf"), "wb") as f:
        f.write(b"%PDF-1.4 body")
    return live_fid


def test_get_file_by_attachment_200_for_live_message(seeded_files):
    from services.file_service import get_file_by_attachment
    live_fid = _seed_messages_table(seeded_files)
    meta, abs_path = get_file_by_attachment(live_fid)
    assert meta["id"] == live_fid
    assert os.path.exists(abs_path)


def test_get_file_by_attachment_404_when_unattached(seeded_files):
    from services.file_service import get_file_by_attachment
    meta = _seed_one_file(seeded_files, owner_id=1)  # fresh file, NOT attached
    with pytest.raises(HTTPException) as exc:
        get_file_by_attachment(meta["id"])
    assert exc.value.status_code == 404


def test_get_file_by_attachment_404_when_only_deleted_message(seeded_files):
    from services.file_service import get_file_by_attachment
    live_fid = _seed_messages_table(seeded_files)
    # the gate currently returns 200 because a LIVE message references it.
    # Now soft-delete that live message too → no live reference left → 404.
    import psycopg2, os
    TEST_DSN = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:235813@localhost:5432/hhb_b2b_test")
    conn = psycopg2.connect(TEST_DSN)
    try:
        cur = conn.cursor()
        cur.execute("UPDATE messages SET deleted_at = now() WHERE attachment_id = %s", (live_fid,))
        conn.commit()
        cur.close()
    finally:
        conn.close()
    with pytest.raises(HTTPException) as exc:
        get_file_by_attachment(live_fid)
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Task 4: public gated /api/chat-attachments/{id} — route-level tests
# ---------------------------------------------------------------------------


def _files_app(seeded_files, monkeypatch):
    """Build a TestClient app with only the files router; patch service get_db + MEDIA_ROOT."""
    import routes.files as rmod
    import services.file_service as svc
    monkeypatch.setattr(svc, "get_db", lambda: psycopg2.connect(
        os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:235813@localhost:5432/hhb_b2b_test")))
    monkeypatch.setattr(svc, "MEDIA_ROOT", seeded_files)
    app = FastAPI()
    app.include_router(rmod.router)
    return TestClient(app)


def test_public_attachment_endpoint_200_for_attached(seeded_files, monkeypatch):
    live_fid = _seed_messages_table(seeded_files)
    # write the physical file so StreamingResponse can read it
    os.makedirs(os.path.join(seeded_files, "2026/07"), exist_ok=True)
    with open(os.path.join(seeded_files, "2026/07/attached.pdf"), "wb") as f:
        f.write(b"%PDF-1.4 body")
    client = _files_app(seeded_files, monkeypatch)
    resp = client.get(f"/api/chat-attachments/{live_fid}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


def test_public_attachment_endpoint_404_for_unattached(seeded_files, monkeypatch):
    meta = _seed_one_file(seeded_files, owner_id=1)  # not attached
    client = _files_app(seeded_files, monkeypatch)
    resp = client.get(f"/api/chat-attachments/{meta['id']}")
    assert resp.status_code == 404


def test_public_attachment_thumbnail_404_for_non_image(seeded_files, monkeypatch):
    live_fid = _seed_messages_table(seeded_files)  # attached file is a PDF (non-image)
    client = _files_app(seeded_files, monkeypatch)
    resp = client.get(f"/api/chat-attachments/{live_fid}/thumbnail")
    assert resp.status_code == 404


def test_public_attachment_content_disposition_safe(seeded_files, monkeypatch):
    """Regression (response-path header injection): a files row whose
    original_name contains quote/CR/LF (e.g. inserted by a code path that
    bypassed sanitize_name, or if sanitize_name were later weakened) must NOT
    leak those chars raw into the Content-Disposition header. The defense under
    test is the ROUTE-LEVEL quote(), NOT save_upload's sanitize_name (that is
    upload-path defense-in-depth). Public + no-auth endpoint → defense must hold.

    To exercise the route defense in isolation, we insert the files row
    directly with the evil name (bypassing sanitize_name), then attach it to a
    live message. If quote() were removed from download_attachment, the raw
    quote/CR/LF would appear in the response header and these asserts would fail.
    """
    evil_name = 'evil"; injection\r\nX-Bad: 1.pdf'
    # write the physical file under MEDIA_ROOT
    os.makedirs(os.path.join(seeded_files, "2026/07"), exist_ok=True)
    with open(os.path.join(seeded_files, "2026/07/evil.pdf"), "wb") as f:
        f.write(b"%PDF-1.4 body")
    # insert a files row with the EVIL original_name (NOT sanitized), then attach.
    # We DROP/RECREATE a minimal messages stub (see _seed_messages_table) so the
    # file is referenced by a live message.
    conn = psycopg2.connect(os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:235813@localhost:5432/hhb_b2b_test"))
    try:
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS messages")
        cur.execute(
            "CREATE TABLE messages (id BIGSERIAL PRIMARY KEY, attachment_id BIGINT NULL, "
            "deleted_at TIMESTAMPTZ NULL)"
        )
        cur.execute(
            "INSERT INTO files (uploaded_by, storage_path, original_name, mime_type, "
            "size_bytes, sha256, is_image, thumbnail_path) VALUES "
            "(1, '2026/07/evil.pdf', %s, 'application/pdf', 10, 'h1', false, NULL)",
            (evil_name,),
        )
        conn.commit()
        cur.execute("SELECT id FROM files WHERE storage_path = '2026/07/evil.pdf'")
        evil_fid = cur.fetchone()[0]
        cur.execute("INSERT INTO messages (attachment_id) VALUES (%s)", (evil_fid,))
        conn.commit()
        cur.close()
    finally:
        conn.close()
    client = _files_app(seeded_files, monkeypatch)
    resp = client.get(f"/api/chat-attachments/{evil_fid}")
    assert resp.status_code == 200
    cd = resp.headers.get("content-disposition", "")
    assert '"' not in cd, f"raw quote leaked into Content-Disposition: {cd!r}"
    assert "\r" not in cd and "\n" not in cd, f"CR/LF leaked into Content-Disposition: {cd!r}"
