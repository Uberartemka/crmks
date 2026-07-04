from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request
from schemas.tasks import NoteCreate

from auth_deps import get_current_user as _get_current_user
from services.notes_service import (
    create_note,
    delete_note,
    list_notes,
    update_note,
)

router = APIRouter(tags=["notes"])


def get_current_user():
    async def _dep(request: Request):
        return _get_current_user(request)

    return _dep


@router.get("/api/notes")
async def list_notes_endpoint(
    tag: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await list_notes(current_user=current_user, tag=tag)


@router.post("/api/notes")
async def create_note_endpoint(
    data: NoteCreate,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await create_note(data=data, current_user=current_user)


@router.patch("/api/notes/{note_id}")
async def update_note_endpoint(
    note_id: int,
    data: NoteCreate,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await update_note(note_id=note_id, data=data, current_user=current_user)


@router.delete("/api/notes/{note_id}")
async def delete_note_endpoint(
    note_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await delete_note(note_id=note_id, current_user=current_user)
