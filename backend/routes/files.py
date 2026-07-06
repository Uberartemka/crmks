"""File upload/download REST endpoints. Thin layer over file_service."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from urllib.parse import quote

from auth_deps import get_current_user as _get_current_user
from services.file_service import save_upload, get_file, get_thumbnail_path, get_file_by_attachment, get_attachment_thumbnail_path

router = APIRouter(tags=["files"])


def get_current_user():
    async def _dep(request: Request):
        return _get_current_user(request)
    return _dep


@router.post("/api/files")
async def upload_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user()),
) -> dict:
    meta = await save_upload(file, current_user)
    # strip internal fields before returning to client
    meta.pop("_storage_path", None)
    meta.pop("sha256", None)
    return meta


@router.get("/api/files/{file_id}")
def download_file(
    file_id: int,
    current_user: dict = Depends(get_current_user()),
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
    current_user: dict = Depends(get_current_user()),
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


@router.get("/api/chat-attachments/{file_id}")
def download_attachment(file_id: int) -> StreamingResponse:
    """Public attachment delivery — NO auth.

    <img src>/CSS cannot send Bearer, so attachments are served without auth,
    gated by EXISTS(messages.attachment_id = file.id AND deleted_at IS NULL).
    Mirrors /api/avatars/{id}. Content-Disposition uses quote() (response-path
    header-injection defense, same as download_file above).
    """
    meta, abs_path = get_file_by_attachment(file_id)

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
        media_type=meta["mime_type"],
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quoted}",
            "Content-Length": str(meta["size_bytes"]),
        },
    )


@router.get("/api/chat-attachments/{file_id}/thumbnail")
def download_attachment_thumbnail(file_id: int) -> StreamingResponse:
    """Public thumbnail — NO auth. 404 if not an image / no thumbnail / not attached."""
    meta, thumb_abs = get_attachment_thumbnail_path(file_id)

    def iterfile():
        with open(thumb_abs, "rb") as f:
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
