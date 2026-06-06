from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends

from auth_deps import get_current_user
from db import _use_pg, get_db
from services.daily_plan_service import generate_daily_plan_for_user

router = APIRouter(prefix="", tags=["agent-daily-plan"])


@router.get("/api/agent/daily-plan")
async def get_daily_plan_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Agent-планировщик: возвращает план на день для текущего пользователя.
    Если плана нет — генерирует новый.
    """
    user_id = current_user["id"]
    today_iso = datetime.now().date().isoformat()

    conn = get_db()
    cursor = conn.cursor()

    if _use_pg:
        cursor.execute(
            "SELECT plan_data FROM daily_plans WHERE user_id = %s AND date = %s",
            (user_id, today_iso),
        )
    else:
        cursor.execute(
            "SELECT plan_data FROM daily_plans WHERE user_id = ? AND date = ?",
            (user_id, today_iso),
        )

    row = cursor.fetchone()
    conn.close()

    if row:
        return {"plan": json.loads(row[0]), "generated": False}

    plan = await generate_daily_plan_for_user(user_id)
    return {"plan": plan, "generated": True}


@router.post("/api/agent/daily-plan/regenerate")
async def regenerate_daily_plan_endpoint(current_user: dict = Depends(get_current_user)):
    """Принудительно перегенерировать план на день."""
    plan = await generate_daily_plan_for_user(current_user["id"])
    return {"plan": plan, "generated": True}
