from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request

from schemas.defects import DefectCreate, DefectUpdate
from auth_deps import get_current_user as _get_current_user
from services.defects_service import (
    create_defect,
    delete_defect,
    list_defects,
    update_defect,
)

router = APIRouter(tags=["defects"])


def get_current_user():
    async def _dep(request: Request):
        return _get_current_user(request)

    return _dep


@router.get("/api/defects")
async def list_defects_endpoint(
    client_id: Optional[int] = None,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await list_defects(current_user=current_user, client_id=client_id)


@router.post("/api/defects")
async def create_defect_endpoint(
    data: DefectCreate,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await create_defect(data=data, current_user=current_user)


@router.patch("/api/defects/{defect_id}")
async def update_defect_endpoint(
    defect_id: int,
    data: DefectUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await update_defect(defect_id=defect_id, data=data, current_user=current_user)


@router.delete("/api/defects/{defect_id}")
async def delete_defect_endpoint(
    defect_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await delete_defect(defect_id=defect_id, current_user=current_user)
