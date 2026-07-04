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


async def save_upload(upload: UploadFile, current_user: dict) -> Dict[str, Any]:
    """Validate, store on disk, generate thumbnail (if image), INSERT, return metadata.

    Raises HTTPException: 413 (too big), 415 (bad MIME/ext), 400 (read error / empty).
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
