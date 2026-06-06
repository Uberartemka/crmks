from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth_deps import get_current_user as _get_current_user

router = APIRouter(tags=["tasks", "notes", "legacy"])


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


# =========================
# Tasks legacy routes
# =========================

@router.get("/api/tasks_legacy")
async def list_tasks_legacy(
    status: Optional[str] = None,
    client_id: Optional[int] = None,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    import services.legacy_tasks_notes as main_mod

    return await main_mod.list_tasks_endpoint(status=status, client_id=client_id, current_user=current_user)


@router.post("/api/tasks_legacy")
async def create_task_legacy(
    body: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    import services.legacy_tasks_notes as main_mod

    return await main_mod.create_task_endpoint(body=body, current_user=current_user)


@router.patch("/api/tasks_legacy/{task_id}")
async def update_task_legacy(
    task_id: int,
    body: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    import services.legacy_tasks_notes as main_mod

    return await main_mod.update_task_endpoint(task_id=task_id, body=body, current_user=current_user)


@router.delete("/api/tasks_legacy/{task_id}")
async def delete_task_legacy(
    task_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    import services.legacy_tasks_notes as main_mod

    return await main_mod.delete_task_endpoint(task_id=task_id, current_user=current_user)


@router.get("/api/tasks_legacy/my")
async def my_tasks_legacy(
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    import services.legacy_tasks_notes as main_mod

    return await main_mod.my_tasks(current_user=current_user)


@router.post("/api/tasks_legacy/{task_id}/done")
async def complete_task_legacy(
    task_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    import services.legacy_tasks_notes as main_mod

    return await main_mod.complete_task(task_id=task_id, current_user=current_user)


@router.post("/api/tasks_legacy/smart-assign")
async def smart_assign_task_legacy(
    body: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    import services.legacy_tasks_notes as main_mod

    return await main_mod.smart_assign_task_endpoint(body=body, current_user=current_user)


# =========================
# Notes legacy routes
# =========================

@router.get("/api/notes_legacy")
async def list_notes_legacy(
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    import services.legacy_tasks_notes as main_mod

    return await main_mod.list_notes(current_user=current_user)


@router.post("/api/notes_legacy")
async def create_note_legacy(
    data: NoteCreate,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    import services.legacy_tasks_notes as main_mod

    return await main_mod.create_note(data=data, current_user=current_user)


@router.patch("/api/notes_legacy/{note_id}")
async def update_note_legacy(
    note_id: int,
    data: NoteCreate,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    import services.legacy_tasks_notes as main_mod

    return await main_mod.update_note(note_id=note_id, data=data, current_user=current_user)


@router.delete("/api/notes_legacy/{note_id}")
async def delete_note_legacy(
    note_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    import services.legacy_tasks_notes as main_mod

    return await main_mod.delete_note(note_id=note_id, current_user=current_user)


# =========================
# Workload legacy routes
# =========================

@router.get("/api/team/workload_legacy")
async def get_team_workload_legacy(
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    import services.legacy_tasks_notes as main_mod

    return await main_mod.get_team_workload_endpoint(current_user=current_user)


@router.get("/api/team/workload_legacy/{user_id}")
async def get_user_workload_legacy(
    user_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    import services.legacy_tasks_notes as main_mod

    return await main_mod.get_user_workload_endpoint(user_id=user_id, current_user=current_user)
