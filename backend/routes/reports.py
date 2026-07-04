from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from auth_deps import get_current_user as _get_current_user
from services.reports_service import get_report_metrics

router = APIRouter(tags=["reports"])


def get_current_user():
    async def _dep(request: Request):
        return _get_current_user(request)

    return _dep


@router.get("/api/reports/metrics")
async def reports_metrics_endpoint(
    period: str = "month",
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    # Admin/manager only
    if current_user.get("role") not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return await get_report_metrics(period=period)
