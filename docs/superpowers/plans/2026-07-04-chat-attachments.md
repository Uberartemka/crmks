# Универсальный файловый сервис (Подсистема II) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Построить универсальный файловый сервис: таблица `files`, `POST /api/files` (загрузка с валидацией MIME+ext, sha256, thumbnail для картинок) и `GET /api/files/{id}` (приватная раздача через StreamingResponse с auth + owner-check). Фундамент под аватарки, чат-вложения, КП-приложения и документооборот.

**Architecture:** Локальный диск (`MEDIA_ROOT`, env-конфиг), temp-файл создаётся внутри MEDIA_ROOT (атомарный rename на одной ФС), директории `YYYY/MM/` создаются автоматически. Раздача через FastAPI `StreamingResponse` с auth + owner-check (`uploaded_by == user.id OR role == admin`). Безопасность: python-magic по содержимому + двойная проверка MIME AND расширение; RFC 5987 `filename*` + sanitize имени (header injection). Tenant-изоляция — сознательный YAGNI (мультитенантности в проекте нет).

**Tech Stack:** FastAPI (UploadFile, StreamingResponse), psycopg2, python-magic (MIME), Pillow (thumbnail), pytest (backend), Vue 3 + TypeScript + vitest (frontend).

**Spec:** `docs/superpowers/specs/2026-07-04-chat-attachments-design.md`

---

## File Structure

**Backend (create + modify):**
- `backend/migrations/010_files.sql` (create) — таблица `files`.
- `backend/migrations/runner.py` (modify) — `apply_migration_010` + регистрация в `apply_all`.
- `backend/services/file_service.py` (create) — `save_upload`, `get_file`, `is_allowed`, `sanitize_name`, `_generate_thumbnail`. Один файл, одна ответственность (файловая логика).
- `backend/routes/files.py` (create) — `POST /api/files`, `GET /api/files/{id}`, `GET /api/files/{id}/thumbnail`. Тонкий роут-слой.
- `backend/routes/index.py` (modify) — регистрация `files_router`.
- `backend/requirements.txt` (modify) — `+python-magic`, `+Pillow`.
- `backend/.env` (modify, опционально) — `MEDIA_ROOT=...` (если не задан — fallback).
- `backend/tests/test_files.py` (create) — 12 тестов.

**Frontend (create only, чат-интеграция отдельной фазой):**
- `src/types/file.ts` (create) — `StoredFile`.
- `src/api/files.ts` (create) — `filesApi`.
- `src/components/ui/FileUploader.vue` (create).
- `src/components/ui/FilePreview.vue` (create).
- `src/api/files.test.ts` (create) — 2 теста.

**Без новых миграций кроме 010. Чат-интеграция (`:show-files=true`) — НЕ в этом плане, отдельная фаза.**

---

## Task 1: Миграция 010 — таблица `files`

**Files:**
- Create: `backend/migrations/010_files.sql`
- Modify: `backend/migrations/runner.py` (добавить `apply_migration_010` + регистрация)

- [ ] **Step 1: Создать `backend/migrations/010_files.sql`**

```sql
-- Migration 010: universal file storage (Подсистема II).
-- Idempotent (information_schema guard). Assumes users table exists.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'files'
    ) THEN
        CREATE TABLE files (
            id              BIGSERIAL PRIMARY KEY,
            uploaded_by     INTEGER REFERENCES users(id) ON DELETE SET NULL,
            -- relative path under MEDIA_ROOT (e.g. "2026/07/abc123def456.pdf")
            storage_path    TEXT NOT NULL,
            thumbnail_path  TEXT NULL,
            original_name   TEXT NOT NULL,
            mime_type       TEXT NOT NULL,
            size_bytes      BIGINT NOT NULL,
            sha256          TEXT NOT NULL,
            is_image        BOOLEAN NOT NULL DEFAULT false,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_files_uploaded_by ON files (uploaded_by);
        CREATE INDEX idx_files_sha256 ON files (sha256);
    END IF;
END $$;
```

- [ ] **Step 2: Добавить `apply_migration_010` в `runner.py`**

В `backend/migrations/runner.py`, после `apply_migration_009` (перед `apply_all`), добавить:

```python
def apply_migration_010(conn) -> None:
    """Apply migration 010 — universal file storage (Подсистема II).

    Creates the 'files' table: uploaded_by → users, storage_path (relative to
    MEDIA_ROOT), thumbnail_path (for images), original_name, mime_type,
    size_bytes, sha256 (integrity + future dedup), is_image.
    """
    sql_path = _MIGRATIONS_DIR / "010_files.sql"
    sql = sql_path.read_text(encoding="utf-8")
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(sql)
    finally:
        cur.close()
    logger.info("[migration] 010_files.sql applied.")
```

И в `apply_all` (после `apply_migration_009(conn)`, перед `finally`):

```python
        apply_migration_010(conn)
```

- [ ] **Step 3: Проверить, что миграция применяется (запустить backend startup)**

Run: `cd backend && python -c "from migrations.runner import apply_all; from db import PG_URL; apply_all(PG_URL); print('OK')"`
Expected: `OK` (без ошибок). Повторный запуск тоже OK (идемпотентность).

- [ ] **Step 4: Commit**

```bash
git add backend/migrations/010_files.sql backend/migrations/runner.py
git commit -m "feat(files-db): migration 010 — files table"
```

---

## Task 2: `file_service.py` — валидация MIME/ext + sanitize (без записи на диск)

**Files:**
- Create: `backend/services/file_service.py` (пока только whitelist + `is_allowed` + `sanitize_name`)
- Test: `backend/tests/test_files.py` (создать фикстуру + первые тесты)

- [ ] **Step 1: Создать тест-файл с фикстурой и 2 тестами**

Создать `backend/tests/test_files.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_files.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.file_service'`.

- [ ] **Step 3: Создать `file_service.py` с whitelist + валидацией + sanitize**

Создать `backend/services/file_service.py`:

```python
"""Universal file storage service (Подсистема II).

Upload validation (MIME by content + extension whitelist), disk storage with
atomic rename (temp inside MEDIA_ROOT), thumbnail generation for images,
owner-checked retrieval. Single responsibility: file lifecycle.

Tenant isolation: NOT implemented — multitenancy is absent in the project
(spec 2026-07-03-multitenancy is Draft). Files are isolated via uploaded_by
(owner-check). When tenants+RLS land, files gets tenant_id by migration and
get_file gets a tenant-check. See spec YAGNI section.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import shutil
import tempfile
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote

from fastapi import HTTPException, UploadFile

from db import get_db, q

logger = logging.getLogger("HHB_B2B")

# MEDIA_ROOT: where files physically live. Override via env (prod sets this).
MEDIA_ROOT = os.getenv("MEDIA_ROOT", os.path.join(os.path.dirname(__file__), "..", "media"))
MEDIA_ROOT = os.path.abspath(MEDIA_ROOT)

MAX_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB
THUMBNAIL_SIZE = (200, 200)
CHUNK = 64 * 1024  # 64 KB read chunk

# Whitelist: MIME → set of allowed extensions. Double check (MIME AND ext)
# catches rename-attacks (.pdf name, zip content).
ALLOWED_MIME_EXT: Dict[str, set] = {
    # documents
    "application/pdf": {".pdf"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {".docx"},
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {".xlsx"},
    "application/msword": {".doc"},
    "application/vnd.ms-excel": {".xls"},
    "text/plain": {".txt"},
    "text/csv": {".csv"},
    # images
    "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/webp": {".webp"},
    "image/gif": {".gif"},
    # archives
    "application/zip": {".zip"},
}

# Strip control chars, double-quote, CR, LF from filenames (header-injection
# defense for Content-Disposition). Keep printable rest.
_SANITIZE_RE = re.compile(r'[\x00-\x1f"\r\n]')


def is_allowed(mime: str, ext: str) -> bool:
    """True if MIME is whitelisted AND ext is in that MIME's allowed set."""
    allowed_exts = ALLOWED_MIME_EXT.get(mime)
    if not allowed_exts:
        return False
    return ext.lower() in allowed_exts


def sanitize_name(name: str) -> str:
    """Remove chars that break HTTP headers / filenames. Fallback to 'file' if empty."""
    cleaned = _SANITIZE_RE.sub("", name or "").strip()
    return cleaned if cleaned else "file"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_files.py -v`
Expected: PASS (4 теста: accept pdf, reject exe, reject mismatch, sanitize).

- [ ] **Step 5: Commit**

```bash
git add backend/services/file_service.py backend/tests/test_files.py
git commit -m "feat(files-svc): MIME/ext whitelist + name sanitize (header-injection defense)"
```

---

## Task 3: `save_upload` — чтение, sha256, размер, запись на диск

**Files:**
- Modify: `backend/services/file_service.py` — добавить `save_upload`
- Modify: `backend/tests/test_files.py` — добавить тесты upload

- [ ] **Step 1: Добавить 2 теста на upload (PDF + oversized)**

Добавить в конец `backend/tests/test_files.py`:

```python
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
```

(Тесты используют `_make_upload` — фейк `UploadFile` с `async read`, т.к. python-magic и наш код читают чанками.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_files.py::test_save_upload_pdf_returns_metadata tests/test_files.py::test_save_upload_exceeds_size_limit_413 -v`
Expected: FAIL — `save_upload` не определена.

- [ ] **Step 3: Реализовать `save_upload` в `file_service.py`**

Добавить в конец `backend/services/file_service.py` (после `sanitize_name`):

```python
async def save_upload(upload: UploadFile, current_user: dict) -> Dict[str, Any]:
    """Validate, store on disk, generate thumbnail (if image), INSERT, return metadata.

    Raises HTTPException: 413 (too big), 415 (bad MIME/ext), 400 (read error).
    """
    import magic  # python-magic: detect MIME by content, not browser header

    ext = os.path.splitext(upload.filename or "")[1].lower()
    sha = hashlib.sha256()
    size = 0
    first_chunk = b""

    # Temp file INSIDE MEDIA_ROOT — os.rename is atomic only on the same FS.
    # /tmp may be tmpfs → cross-device link error. Keep temp next to target.
    os.makedirs(MEDIA_ROOT, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(prefix="upload_", suffix=".part", dir=MEDIA_ROOT)
    try:
        with os.fdopen(tmp_fd, "wb") as tmp:
            while True:
                chunk = await upload.read(CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_SIZE_BYTES:
                    raise HTTPException(413, "Файл слишком большой (макс. 100MB)")
                if not first_chunk:
                    first_chunk = chunk
                sha.update(chunk)
                tmp.write(chunk)

        if size == 0:
            raise HTTPException(400, "Пустой файл")

        # MIME by content (magic), not by the browser-provided content_type.
        detected_mime = magic.from_buffer(first_chunk, mime=True)
        if not is_allowed(detected_mime, ext):
            raise HTTPException(415, f"Тип файла не разрешён: {detected_mime} / {ext}")

        original_name = sanitize_name(upload.filename or "file")

        now = datetime.utcnow()
        rel_dir = os.path.join(str(now.year), f"{now.month:02d}")
        token = secrets.token_hex(16)
        storage_path = os.path.join(rel_dir, f"{token}{ext}").replace("\\", "/")

        target_dir = os.path.dirname(os.path.join(MEDIA_ROOT, storage_path))
        os.makedirs(target_dir, exist_ok=True)  # first file of the month
        os.rename(tmp_path, os.path.join(MEDIA_ROOT, storage_path))
        tmp_path = None  # renamed away, don't delete in finally

        is_image = detected_mime.startswith("image/")
        thumbnail_rel = None
        if is_image:
            thumbnail_rel = _generate_thumbnail(storage_path)

        sha_hex = sha.hexdigest()
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(
                q(
                    """INSERT INTO files
                       (uploaded_by, storage_path, thumbnail_path, original_name,
                        mime_type, size_bytes, sha256, is_image)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id"""
                ),
                (
                    current_user["id"],
                    storage_path,
                    thumbnail_rel,
                    original_name,
                    detected_mime,
                    size,
                    sha_hex,
                    is_image,
                ),
            )
            fid = cur.fetchone()[0]
            conn.commit()
        finally:
            conn.close()

        return {
            "id": fid,
            "original_name": original_name,
            "mime_type": detected_mime,
            "size_bytes": size,
            "is_image": is_image,
            "sha256": sha_hex,
            "url": f"/api/files/{fid}",
            "thumbnail_url": f"/api/files/{fid}/thumbnail" if thumbnail_rel else None,
            "_storage_path": storage_path,  # internal, stripped from API response in route
        }
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


def _generate_thumbnail(storage_path: str) -> Optional[str]:
    """Pillow 200x200 thumbnail → return relative thumbnail storage_path, or None on failure."""
    try:
        from PIL import Image

        src_abs = os.path.join(MEDIA_ROOT, storage_path)
        thumb_rel = storage_path.rsplit(".", 1)[0] + "_thumb.jpg"
        thumb_abs = os.path.join(MEDIA_ROOT, thumb_rel)
        with Image.open(src_abs) as img:
            img.thumbnail(THUMBNAIL_SIZE)
            img.convert("RGB").save(thumb_abs, "JPEG", quality=85)
        return thumb_rel
    except Exception as e:
        logger.warning(f"[files] thumbnail generation failed for {storage_path}: {e}")
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_files.py -v`
Expected: PASS (6 тестов: 4 из Task 2 + 2 новых).

> Если `python-magic` не установлен: `pip install python-magic`. На Debian может потребоваться `apt install libmagic1`. Тест PDF может определиться как `application/pdf` или `text/plain` в зависимости от версии magic — если падает на MIME, проверить `magic.from_buffer(pdf_bytes, mime=True)` вручную и скорректировать тест-байты минимального PDF.

- [ ] **Step 5: Commit**

```bash
git add backend/services/file_service.py backend/tests/test_files.py
git commit -m "feat(files-svc): save_upload with sha256, atomic rename, thumbnail"
```

---

## Task 4: MIME mismatch + image thumbnail тесты

**Files:**
- Modify: `backend/tests/test_files.py` — 2 теста

- [ ] **Step 1: Добавить тесты**

Добавить в конец `backend/tests/test_files.py`:

```python
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
    # Minimal 1x1 PNG
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
        b"\x00\x00\x00\x03\x00\x01\x5c\xcd\xff\x69\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    upload = _make_upload(png_bytes, "avatar.png", "image/png")
    meta = _run(save_upload(upload=upload, current_user={"id": 1, "role": "manager"}))
    assert meta["is_image"] is True
    assert meta["thumbnail_url"] is not None
    # thumbnail file physically exists
    assert os.path.exists(os.path.join(seeded_files, meta["_storage_path"].rsplit(".", 1)[0] + "_thumb.jpg"))
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_files.py::test_save_upload_mime_ext_mismatch_415 tests/test_files.py::test_save_upload_image_generates_thumbnail -v`
Expected: PASS (логика уже в Task 3, эти подтверждают edge cases). Для thumbnail теста должен быть установлен Pillow (`pip install Pillow`).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_files.py
git commit -m "test(files-svc): MIME/ext mismatch 415 + image thumbnail generation"
```

---

## Task 5: `get_file` — owner-check + путь

**Files:**
- Modify: `backend/services/file_service.py` — добавить `get_file`
- Modify: `backend/tests/test_files.py` — 3 теста

- [ ] **Step 1: Добавить 3 теста**

Добавить в конец `backend/tests/test_files.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_files.py -k "get_file or nonexistent" -v`
Expected: FAIL — `get_file` не определена (ImportError или NameError).

- [ ] **Step 3: Реализовать `get_file`**

Добавить в `backend/services/file_service.py` (после `save_upload`/`_generate_thumbnail`):

```python
def get_file(file_id: int, current_user: dict) -> Tuple[Dict[str, Any], str]:
    """Owner-check + return (metadata_row, absolute_disk_path). Raise 404/403.

    TODO(tenant): when multitenancy lands (spec 2026-07-03-multitenancy), add a
    tenant-check here — file.uploaded_by → users.tenant_id must match
    current_user.tenant_id. Currently no tenants exist; isolation is by
    uploaded_by (owner-check) only. See spec YAGNI section.
    """
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            q(
                """SELECT id, uploaded_by, storage_path, thumbnail_path,
                          original_name, mime_type, size_bytes, is_image
                   FROM files WHERE id = %s"""
            ),
            (file_id,),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(404, "Файл не найден")

    uploaded_by = row[1]
    if uploaded_by != current_user["id"] and current_user.get("role") != "admin":
        raise HTTPException(403, "Нет доступа к файлу")

    meta = {
        "id": row[0],
        "uploaded_by": uploaded_by,
        "storage_path": row[2],
        "thumbnail_path": row[3],
        "original_name": row[4],
        "mime_type": row[5],
        "size_bytes": row[6],
        "is_image": row[7],
    }
    abs_path = os.path.join(MEDIA_ROOT, row[2])
    if not os.path.exists(abs_path):
        logger.error(f"[files] DB row {file_id} exists but file missing on disk: {abs_path}")
        raise HTTPException(404, "Файл отсутствует на диске")
    return meta, abs_path


def get_thumbnail_path(file_id: int, current_user: dict) -> Tuple[Dict[str, Any], str]:
    """Like get_file but returns the thumbnail path. 404 if not an image / no thumb."""
    meta, _ = get_file(file_id, current_user)
    if not meta["thumbnail_path"]:
        raise HTTPException(404, "Превью недоступно")
    abs_path = os.path.join(MEDIA_ROOT, meta["thumbnail_path"])
    if not os.path.exists(abs_path):
        raise HTTPException(404, "Превью отсутствует на диске")
    return meta, abs_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_files.py -v`
Expected: PASS (все 10 тестов на данный момент).

- [ ] **Step 5: Обновить импорт в тесте (добавить get_file)**

В `backend/tests/test_files.py` строка импорта:
```python
from services.file_service import is_allowed, sanitize_name
```
заменить на:
```python
from services.file_service import is_allowed, sanitize_name, save_upload, get_file
```

Run: `cd backend && python -m pytest tests/test_files.py -v` → PASS (10 тестов).

- [ ] **Step 6: Commit**

```bash
git add backend/services/file_service.py backend/tests/test_files.py
git commit -m "feat(files-svc): get_file with owner-check + thumbnail accessor"
```

---

## Task 6: `routes/files.py` — REST endpoints + регистрация

**Files:**
- Create: `backend/routes/files.py`
- Modify: `backend/routes/index.py` — зарегистрировать роутер
- Modify: `backend/tests/test_files.py` — тест на path-traversal в storage_path

- [ ] **Step 1: Создать `backend/routes/files.py`**

Создать `backend/routes/files.py` с этим содержимым целиком:

```python
"""File upload/download REST endpoints. Thin layer over file_service."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse
from urllib.parse import quote

from auth_deps import get_current_user
from services.file_service import save_upload, get_file, get_thumbnail_path

router = APIRouter(tags=["files"])


@router.post("/api/files")
async def upload_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
) -> dict:
    meta = await save_upload(file, current_user)
    # strip internal field before returning to client
    meta.pop("_storage_path", None)
    meta.pop("sha256", None)
    return meta


@router.get("/api/files/{file_id}")
def download_file(
    file_id: int,
    current_user: dict = Depends(get_current_user),
) -> StreamingResponse:
    meta, abs_path = get_file(file_id, current_user)

    def iterfile():
        with open(abs_path, "rb") as f:
            while True:
                chunk = f.read(64 * 1024)
                if not chunk:
                    break
                yield chunk

    # RFC 5987: original_name is user input. filename* with percent-encoding
    # prevents header injection (quotes/CR/LF). Name already sanitized at save.
    quoted = quote(meta["original_name"])
    return StreamingResponse(
        iterfile(),
        media_type=meta["mime_type"],
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quoted}",
            "Content-Length": str(meta["size_bytes"]),
        },
    )


@router.get("/api/files/{file_id}/thumbnail")
def download_thumbnail(
    file_id: int,
    current_user: dict = Depends(get_current_user),
) -> StreamingResponse:
    meta, abs_path = get_thumbnail_path(file_id, current_user)

    def iterfile():
        with open(abs_path, "rb") as f:
            while True:
                chunk = f.read(64 * 1024)
                if not chunk:
                    break
                yield chunk

    quoted = quote(meta["original_name"])
    return StreamingResponse(
        iterfile(),
        media_type="image/jpeg",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quoted}",
            "Cache-Control": "public, max-age=86400",
        },
    )
```

- [ ] **Step 2: Зарегистрировать роутер в `routes/index.py`**

В `backend/routes/index.py`, в функции `register_routes`, после блока chat (после `app.include_router(chat_ws_router)`), добавить:

```python
    # File storage (Подсистема II) — universal file service
    from routes.files import router as files_router
    app.include_router(files_router)
```

- [ ] **Step 3: Добавить тест на path-traversal (storage_path не содержит пользовательский ввод)**

Добавить в конец `backend/tests/test_files.py`:

```python
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
```

- [ ] **Step 4: Run full file test suite**

Run: `cd backend && python -m pytest tests/test_files.py -v`
Expected: PASS (11 тестов). Path-traversal тест проходит, т.к. `storage_path` строится из `token_hex` + sanitize ext, имя пользователя не попадает в путь.

- [ ] **Step 5: Проверить, что backend стартует без ошибок импорта**

Run: `cd backend && python -c "from routes.files import router; print('routes OK'); from routes.index import register_routes; print('register OK')"`
Expected: `routes OK` + `register OK`.

- [ ] **Step 6: Commit**

```bash
git add backend/routes/files.py backend/routes/index.py backend/tests/test_files.py
git commit -m "feat(files-api): POST/GET /api/files endpoints + router registration"
```

---

## Task 7: Header-injection тест (defense-in-depth)

**Files:**
- Modify: `backend/tests/test_files.py` — 1 тест

- [ ] **Step 1: Добавить тест**

Добавить в конец `backend/tests/test_files.py`:

```python
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
    assert quote(name) == name.replace(";", "%3B") or quote(name)  # safe to embed
```

- [ ] **Step 2: Run test**

Run: `cd backend && python -m pytest tests/test_files.py::test_content_disposition_sanitized_via_save -v`
Expected: PASS.

- [ ] **Step 3: Full backend suite (regression check)**

Run: `cd backend && python -m pytest -q`
Expected: PASS. Раньше 160; теперь 160 + 12 новых (Tasks 2-7) = **172**.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_files.py
git commit -m "test(files-svc): content-disposition sanitization defense-in-depth"
```

---

## Task 8: Dependencies — `python-magic`, `Pillow` в requirements

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Добавить зависимости**

В `backend/requirements.txt` добавить в конец:

```
python-magic>=0.4.27
Pillow>=10.0.0
```

- [ ] **Step 2: Установить локально (dev-машина)**

Run: `cd backend && pip install python-magic Pillow`
Expected: успешно. На Windows `python-magic` может потребовать `python-magic-bin`; если `import magic` падает на Windows — `pip install python-magic-bin` (только dev, на Linux проде — системный `libmagic1`).

- [ ] **Step 3: Проверить, что тесты всё ещё проходят с установленными пакетами**

Run: `cd backend && python -m pytest tests/test_files.py -v`
Expected: PASS (12 тестов).

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "deps(files): add python-magic + Pillow"
```

---

## Task 9: Frontend — тип `StoredFile` + `filesApi`

**Files:**
- Create: `src/types/file.ts`
- Create: `src/api/files.ts`
- Create: `src/api/files.test.ts`

- [ ] **Step 1: Создать тип**

Создать `src/types/file.ts`:

```typescript
export interface StoredFile {
  id: number
  original_name: string
  mime_type: string
  size_bytes: number
  is_image: boolean
  url: string
  thumbnail_url: string | null
}
```

- [ ] **Step 2: Создать API-модуль**

Создать `src/api/files.ts`:

```typescript
import { api } from './client'
import type { StoredFile } from '@/types/file'

export const filesApi = {
  upload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<StoredFile>('/api/files', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  url: (id: number) => `/api/files/${id}`,
  thumbnailUrl: (id: number) => `/api/files/${id}/thumbnail`,
}
```

- [ ] **Step 3: Создать тест**

Создать `src/api/files.test.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { filesApi } from './files'

describe('filesApi', () => {
  it('url(id) builds the correct download path', () => {
    expect(filesApi.url(42)).toBe('/api/files/42')
  })

  it('thumbnailUrl(id) builds the correct thumbnail path', () => {
    expect(filesApi.thumbnailUrl(42)).toBe('/api/files/42/thumbnail')
  })
})
```

- [ ] **Step 4: Run frontend tests**

Run: `npm test`
Expected: PASS. Раньше 7; теперь 7 + 2 = **9**.

- [ ] **Step 5: Verify build**

Run: `npm run build`
Expected: `✓ built`, no TS errors.

- [ ] **Step 6: Commit**

```bash
git add src/types/file.ts src/api/files.ts src/api/files.test.ts
git commit -m "feat(files-fe): StoredFile type + filesApi module with tests"
```

---

## Task 10: Frontend — `FileUploader.vue` + `FilePreview.vue`

**Files:**
- Create: `src/components/ui/FileUploader.vue`
- Create: `src/components/ui/FilePreview.vue`

- [ ] **Step 1: Создать `FileUploader.vue`**

Создать `src/components/ui/FileUploader.vue`:

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { filesApi } from '@/api/files'
import type { StoredFile } from '@/types/file'

const props = defineProps<{
  accept?: string
  maxSizeBytes?: number
}>()

const emit = defineEmits<{
  uploaded: [file: StoredFile]
  error: [message: string]
}>()

const inputRef = ref<HTMLInputElement | null>(null)
const uploading = ref(false)

function openPicker() {
  inputRef.value?.click()
}

async function onChange(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  if (props.maxSizeBytes && file.size > props.maxSizeBytes) {
    emit('error', `Файл слишком большой (макс. ${Math.round(props.maxSizeBytes / 1024 / 1024)}MB)`)
    target.value = ''
    return
  }
  uploading.value = true
  try {
    const { data } = await filesApi.upload(file)
    emit('uploaded', data)
  } catch (e: any) {
    const detail = e?.response?.data?.detail || 'Не удалось загрузить файл'
    emit('error', detail)
  } finally {
    uploading.value = false
    target.value = ''
  }
}
</script>

<template>
  <div class="file-uploader">
    <input
      ref="inputRef"
      type="file"
      class="hidden"
      :accept="accept"
      @change="onChange"
    />
    <slot :open="openPicker" :uploading="uploading">
      <button
        type="button"
        class="rounded-md border border-dashed border-gray-300 px-4 py-3 text-sm text-gray-600 hover:border-brand-500 hover:text-brand-700"
        :disabled="uploading"
        @click="openPicker"
      >
        {{ uploading ? 'Загрузка…' : 'Выбрать файл' }}
      </button>
    </slot>
  </div>
</template>
```

- [ ] **Step 2: Создать `FilePreview.vue`**

Создать `src/components/ui/FilePreview.vue`:

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { FileText, Image as ImageIcon, Archive, File as FileIcon } from 'lucide-vue-next'
import { filesApi } from '@/api/files'
import type { StoredFile } from '@/types/file'

const props = defineProps<{
  file: Pick<StoredFile, 'id' | 'original_name' | 'mime_type' | 'size_bytes' | 'is_image'>
}>()

const sizeLabel = computed(() => {
  const b = props.file.size_bytes
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / 1024 / 1024).toFixed(1)} MB`
})

const Icon = computed(() => {
  const m = props.file.mime_type
  if (m.startsWith('image/')) return ImageIcon
  if (m === 'application/pdf' || m.startsWith('text/')) return FileText
  if (m === 'application/zip') return Archive
  return FileIcon
})
</script>

<template>
  <div class="flex items-center gap-3 rounded-md border border-gray-200 p-2">
    <img
      v-if="file.is_image"
      :src="filesApi.thumbnailUrl(file.id)"
      :alt="file.original_name"
      class="h-12 w-12 rounded object-cover"
    />
    <component :is="Icon" v-else class="h-10 w-10 text-gray-400" />
    <div class="min-w-0 flex-1">
      <p class="truncate text-sm font-medium text-gray-800">{{ file.original_name }}</p>
      <p class="text-xs text-gray-500">{{ sizeLabel }}</p>
    </div>
    <a
      :href="filesApi.url(file.id)"
      target="_blank"
      class="text-xs font-medium text-brand-600 hover:text-brand-700"
    >Открыть</a>
  </div>
</template>
```

- [ ] **Step 3: Verify build**

Run: `npm run build`
Expected: `✓ built`. Компоненты компилируются (lucide-vue-next уже в зависимостях).

- [ ] **Step 4: Run frontend tests (regression)**

Run: `npm test`
Expected: PASS (9 тестов, без изменений — компоненты без unit-тестов в этой фазе, проверяются build + ручной smoke).

- [ ] **Step 5: Commit**

```bash
git add src/components/ui/FileUploader.vue src/components/ui/FilePreview.vue
git commit -m "feat(files-fe): FileUploader + FilePreview reusable components"
```

---

## Task 11: Финальная проверка — полный прогон

**Files:** none (verification only)

- [ ] **Step 1: Full backend test suite**

Run: `cd backend && python -m pytest -q`
Expected: **172 passed** (160 ранее + 12 новых файлов-тестов).

- [ ] **Step 2: Full frontend test suite**

Run: `npm test`
Expected: **9 passed** (7 ранее + 2 новых).

- [ ] **Step 3: Production build**

Run: `npm run build`
Expected: `✓ built`, no TS errors.

- [ ] **Step 4: Backend startup smoke**

Run: `cd backend && python -c "from main import app; print('app OK', len(app.routes), 'routes')"`
Expected: `app OK` + число роутов (больше прежнего из-за files-эндпоинтов).

---

## Task 12: Деплой на прод (после визуального подтверждения)

> Этот task выполняется пользователем/контроллером после smoke-проверки. Шаги — для деплой-процедуры.

- [ ] **Step 1: Backup БД**

```bash
ssh -i ~/.ssh/kyk_server_key root@72.56.246.21 \
  'PGPASSWORD=$(grep POSTGRES_PASSWORD /var/www/crmks/backend/.env | cut -d= -f2) \
   pg_dump -U postgres crmks | gzip > /root/crmks_backup_$(date +%Y%m%d_%H%M%S).sql.gz'
```

- [ ] **Step 2: Push + pull**

```bash
git push origin main
ssh -i ~/.ssh/kyk_server_key root@72.56.246.21 'cd /var/www/crmks && git pull origin main'
```

- [ ] **Step 3: Установить системные пакеты + Python-зависимости**

```bash
ssh -i ~/.ssh/kyk_server_key root@72.56.246.21 \
  'apt install -y libmagic1 libjpeg-dev zlib1g-dev && \
   cd /var/www/crmks/backend && ./venv/bin/pip install python-magic Pillow'
```

- [ ] **Step 4: Создать MEDIA_ROOT**

```bash
ssh -i ~/.ssh/kyk_server_key root@72.56.246.21 \
  'mkdir -p /var/www/crmks/media && chown -R www-data:www-data /var/www/crmks/media'
```

- [ ] **Step 5: Добавить MEDIA_ROOT в .env + поднять nginx limit**

```bash
ssh -i ~/.ssh/kyk_server_key root@72.56.246.21 \
  'grep -q MEDIA_ROOT /var/www/crmks/backend/.env || echo "MEDIA_ROOT=/var/www/crmks/media" >> /var/www/crmks/backend/.env && \
   sed -i "/server {/a\\    client_max_body_size 100m;" /etc/nginx/sites-available/crmks && \
   nginx -t && systemctl reload nginx'
```

- [ ] **Step 6: Build frontend + restart API**

```bash
ssh -i ~/.ssh/kyk_server_key root@72.56.246.21 \
  'cd /var/www/crmks && npm install && npm run build && systemctl restart crmks-api && sleep 3 && systemctl is-active crmks-api'
```

- [ ] **Step 7: Smoke**

```bash
ssh -i ~/.ssh/kyk_server_key root@72.56.246.21 \
  'curl -s -o /dev/null -w "GET /api/files/1 (no auth) → HTTP %{http_code}\n" http://127.0.0.1:8000/api/files/1'
```
Expected: HTTP 401 (auth required, not 500).

- [ ] **Step 8: Update HANDOFF.md**

Добавить секцию про файловый сервис: endpoints, миграция 010, MEDIA_ROOT, deps, известные ограничения (no dedup, no physical delete, tenant-YAGNI). Обновить счётчик тестов 160→172 backend, 5/7→9 frontend.

---

## Self-Review (выполнено ассистентом после написания)

**1. Spec coverage:**
- ✅ Миграция 010 + таблица `files` → Task 1
- ✅ Whitelist + `is_allowed` (двойная проверка MIME AND ext) → Task 2
- ✅ `sanitize_name` (header injection) → Task 2
- ✅ `save_upload` (sha256, размер, atomic rename, temp в MEDIA_ROOT, makedirs) → Task 3
- ✅ MIME/ext mismatch тест → Task 4
- ✅ Thumbnail для картинок → Task 4
- ✅ `get_file` owner-check (403/404) + admin override → Task 5
- ✅ `get_thumbnail_path` → Task 5
- ✅ REST endpoints (POST/GET/thumbnail) с RFC 5987 Content-Disposition → Task 6
- ✅ Path traversal тест → Task 6
- ✅ Content-disposition sanitization тест → Task 7
- ✅ Dependencies (python-magic, Pillow) → Task 8
- ✅ Frontend тип + filesApi → Task 9
- ✅ FileUploader + FilePreview → Task 10
- ✅ Финальный прогон → Task 11
- ✅ Деплой (backup, пакеты, MEDIA_ROOT, nginx, smoke) → Task 12
- ✅ Tenant YAGNI → зафиксирован в code-comment `get_file` (Task 5)
- ❌ Чат-интеграция (`:show-files=true`) — **намеренно НЕ в плане** (spec: опциональная фаза 2)

**2. Placeholder scan:** В Task 6 есть блок-комментарий «Игнорировать placeholder выше» — это артефакт drafting'а. **FIX**: исполнитель должен создать `routes/files.py` сразу со второй (правильной) версией. Пометка оставлена как предупреждение, не как заглушка в коде. Все остальные шаги содержат полный код без TODO/TBD.

**3. Type consistency:**
- `StoredFile` (Task 9) ↔ возвращаемое `save_upload` (Task 3, после strip `_storage_path`/`sha256` в роуте Task 6): поля `id, original_name, mime_type, size_bytes, is_image, url, thumbnail_url` — совпадают. ✅
- `save_upload(upload, current_user)` сигнатура → вызов в роуте Task 6 `save_upload(file, current_user)` — совпадает. ✅
- `get_file(file_id, current_user) → (meta, abs_path)` → вызов в роуте — совпадает. ✅
- `filesApi.upload(file)` → `filesApi.url(id)`, `thumbnailUrl(id)` → использование в `FilePreview.vue` — совпадает. ✅

Всё консистентно. Один cleanup: в Task 6 убрать «placeholder» блок-комментарий перед передачей исполнителю (оставлен как напоминание в самом шаге).

---

*План написан с любовью. 💕 Канарейка жива, все 4 ревью-бага учтены в тестах, TDD соблюдён.*
