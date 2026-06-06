from __future__ import annotations

import logging
from typing import Any

from services.daily_plan_service import (
    generate_daily_plan_for_user as _generate_daily_plan_for_user,
    get_daily_plan_for_team_or_user as _get_daily_plan_for_team_or_user,
    generate_daily_plan_assign_unassigned_leads as _generate_daily_plan_assign_unassigned_leads,
)

logger = logging.getLogger("HHB_B2B")


async def generate_daily_plan_for_user(user_id: int, db_conn: Any = None) -> dict[str, Any]:
    """
    Thin wrapper around `services.daily_plan_service.generate_daily_plan_for_user`.

    Kept in a separate module so that `main.py` does not carry the heavy async SQL + AI logic.
    """
    return await _generate_daily_plan_for_user(user_id=user_id, db_conn=db_conn)


def get_daily_plan_for_team_or_user(current_user: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Contract for frontend `/api/daily-plan`.

    DailyPlanItem (crmks/src/types/plan.ts) expects:
      - completed_calls (not completed_today)
    """
    plans = _get_daily_plan_for_team_or_user(current_user)

    out: list[dict[str, Any]] = []
    for p in plans:
        # copy to avoid mutating underlying dict
        normalized = dict(p)
        if "completed_today" in normalized and "completed_calls" not in normalized:
            normalized["completed_calls"] = normalized.pop("completed_today")
        out.append(normalized)

    return out


def generate_daily_plan_assign_unassigned_leads(current_user: dict[str, Any]) -> dict[str, Any]:
    return _generate_daily_plan_assign_unassigned_leads(current_user)


async def run_daily_plans_scheduler() -> None:
    """Generate plans for all employees/managers each morning (scheduler entrypoint)."""
    # We delegate the iteration to the daily_plan_service implementation to keep logic centralized.
    from db import get_db, q, _use_pg

    conn = get_db()
    cursor = conn.cursor()

    try:
        if _use_pg:
            cursor.execute("SELECT id FROM users WHERE role IN ('employee', 'manager')")
        else:
            cursor.execute("SELECT id FROM users WHERE role IN ('employee', 'manager')")

        users = cursor.fetchall()

        for (user_id,) in users:
            try:
                await generate_daily_plan_for_user(user_id)
                logger.info(f"[run_daily_plans] План сгенерирован для user_id={user_id}")
            except Exception as e:
                logger.error(f"[run_daily_plans] Ошибка для user_id={user_id}: {e}")

        logger.info(f"[run_daily_plans] Планы сгенерированы для {len(users)} сотрудников")
    finally:
        conn.close()
