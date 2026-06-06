from __future__ import annotations

from fastapi import APIRouter, Depends

from auth_deps import get_current_user
from services.ai_plan_service import (
    generate_daily_plan_assign_unassigned_leads,
    get_daily_plan_for_team_or_user,
)

router = APIRouter(prefix="", tags=["daily-plan"])


@router.get("/api/daily-plan")
def get_daily_plan(current_user: dict = Depends(get_current_user)):
    return get_daily_plan_for_team_or_user(current_user)


@router.post("/api/daily-plan/generate")
def generate_daily_plan(current_user: dict = Depends(get_current_user)):
    return generate_daily_plan_assign_unassigned_leads(current_user)
