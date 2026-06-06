from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from auth_deps import get_current_user as _get_current_user

router = APIRouter(tags=["notes"])


def get_current_user():
    async def _dep(request: Request):
        return _get_current_user(request)

    return _dep


class NoteCreate(BaseModel):
    title: str
    content: str
    color: Optional[str] = "yellow"
    pinned: bool = False
    tags: List[str] = []
    client_id: Optional[int] = None


# -------------------------
# Notes wrappers
# -------------------------

@router.get("/api/notes")
async def list_notes_wrapper(
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    import services.legacy_tasks_notes as main_mod

    return await main_mod.list_notes(current_user=current_user)


@router.post("/api/notes")
async def create_note_wrapper(
    data: NoteCreate,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    import services.legacy_tasks_notes as main_mod

    return await main_mod.create_note(data=data, current_user=current_user)


@router.patch("/api/notes/{note_id}")
async def update_note_wrapper(
    note_id: int,
    data: NoteCreate,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    import services.legacy_tasks_notes as main_mod

    return await main_mod.update_note(note_id=note_id, data=data, current_user=current_user)


@router.delete("/api/notes/{note_id}")
async def delete_note_wrapper(
    note_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    import services.legacy_tasks_notes as main_mod

    return await main_mod.delete_note(note_id=note_id, current_user=current_user)
