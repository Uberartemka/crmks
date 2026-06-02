from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request

from auth_deps import get_current_user as _get_current_user
from services.tasks_service import (
    complete_task,
    create_task_endpoint,
    delete_task_endpoint,
    list_tasks_endpoint,
    my_tasks,
    update_task_endpoint,
)

router = APIRouter(tags=["tasks"])


def get_current_user():
    async def _dep(request: Request):
        return _get_current_user(request)

    return _dep


@router.get("/api/tasks")
async def list_tasks(
    status: Optional[str] = None,
    client_id: Optional[int] = None,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await list_tasks_endpoint(
        status=status,
        client_id=client_id,
        current_user=current_user,
    )


@router.post("/api/tasks")
async def create_task(
    body: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await create_task_endpoint(
        body=body,
        current_user=current_user,
    )


@router.patch("/api/tasks/{task_id}")
async def update_task(
    task_id: int,
    body: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await update_task_endpoint(
        task_id=task_id,
        body=body,
        current_user=current_user,
    )


@router.delete("/api/tasks/{task_id}")
async def delete_task(
    task_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await delete_task_endpoint(
        task_id=task_id,
        current_user=current_user,
    )


@router.get("/api/tasks/my")
async def my_tasks_endpoint(current_user: Dict[str, Any] = Depends(get_current_user())):
    return await my_tasks(
        current_user=current_user,
    )


@router.post("/api/tasks/{task_id}/done")
async def complete_task_endpoint(
    task_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await complete_task(
        task_id=task_id,
        current_user=current_user,
    )
