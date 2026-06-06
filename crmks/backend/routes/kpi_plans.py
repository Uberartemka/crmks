from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from db import get_db, q

from services.kpi_plans_service import build_kpi_payload

router = APIRouter(tags=["kpi", "plans"])


from auth_deps import get_current_user as _get_current_user


def get_current_user():
    async def _dep(request: Request):
        return _get_current_user(request)

    return _dep


class KpiPlansQuery(BaseModel):
    month: Optional[int] = None
    year: Optional[int] = None


@router.get("/api/kpi-plans")
async def get_kpi_plans(
    month: Optional[int] = None,
    year: Optional[int] = None,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    from datetime import datetime

    now = datetime.now()
    m = month or (now.month)
    y = year or (now.year)

    if not (1 <= m <= 12):
        raise HTTPException(status_code=400, detail="Invalid month")
    if y < 1970 or y > 2100:
        raise HTTPException(status_code=400, detail="Invalid year")

    payload = build_kpi_payload(current_user=current_user, year=y, month=m)
    return payload
