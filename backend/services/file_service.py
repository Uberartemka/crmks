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
