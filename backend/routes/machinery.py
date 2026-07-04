from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request

from schemas.machinery import MachineryCreate, MachineryUpdate
from auth_deps import get_current_user as _get_current_user
from services.machinery_service import (
    create_machinery,
    delete_machinery,
    list_machinery,
    update_machinery,
)

router = APIRouter(tags=["machinery"])


def get_current_user():
    async def _dep(request: Request):
        return _get_current_user(request)

    return _dep


@router.get("/api/machinery")
async def list_machinery_endpoint(
    client_id: Optional[int] = None,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await list_machinery(current_user=current_user, client_id=client_id)


@router.post("/api/machinery")
async def create_machinery_endpoint(
    data: MachineryCreate,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await create_machinery(data=data, current_user=current_user)


@router.patch("/api/machinery/{machinery_id}")
async def update_machinery_endpoint(
    machinery_id: int,
    data: MachineryUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await update_machinery(machinery_id=machinery_id, data=data, current_user=current_user)


@router.delete("/api/machinery/{machinery_id}")
async def delete_machinery_endpoint(
    machinery_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await delete_machinery(machinery_id=machinery_id, current_user=current_user)
