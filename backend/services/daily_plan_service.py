from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from db import _use_pg, get_db, q
from routes.ai_claude_agent import call_claude
from utils.ai_utils import parse_ai_json

logger = logging.getLogger("HHB_B2B")


async def generate_daily_plan_for_user(user_id: int, db_conn=None) -> dict[str, Any]:
    """
    Внутренняя функция для генерации плана на день для конкретного пользователя.
    Используется и в эндпойнте, и в планировщике.
    """
    from db_async import get_async_pool

    today_date = datetime.now().date()
    today_iso = today_date.isoformat()  # оставляем как строку, если где-то ещё пригодится
    now = datetime.now().isoformat()

    # db_conn предполагается как asyncpg.Connection
    if db_conn is not None:
        conn = db_conn
        own_conn = False
    else:
        pool = await get_async_pool()
        conn = None
        own_conn = True

    try:
        if own_conn:
            async with pool.acquire() as async_conn:
                conn = async_conn

                open_tasks = await conn.fetch(
                    """
                    SELECT id, title, priority, due_date
                    FROM tasks
                    WHERE assigned_to = $1 AND status != 'done'
                    ORDER BY CASE priority
                        WHEN 'urgent' THEN 1
                        WHEN 'high' THEN 2
                        WHEN 'normal' THEN 3
                        ELSE 4
                    END, due_date ASC
                    """,
                    user_id,
                )

                hot_statuses = ["новый", "горячий", "в_работе"]
                hot_leads = await conn.fetch(
                    """
                    SELECT id, name, status
                    FROM parsed_leads
                    WHERE assigned_to = $1 AND status = ANY($2::text[])
                    """,
                    user_id,
                    hot_statuses,
                )

                stale_dt_param = str((datetime.now() - timedelta(days=2)).isoformat())
                stale_leads = await conn.fetch(
                    """
                    SELECT id, name, updated_at
                    FROM parsed_leads
                    WHERE assigned_to = $1
                      AND status NOT IN ('закрыт', 'отказ')
                      AND updated_at < $2
                    ORDER BY updated_at ASC
                    LIMIT 10
                    """,
                    user_id,
                    stale_dt_param,
                )

                tasks_text = (
                    "\n".join(
                        [
                            f"- [{t['priority']}] {t['title']}, дедлайн: {str(t['due_date'])[:10] if t['due_date'] else 'нет'}"
                            for t in open_tasks[:15]
                        ]
                    )
                    if open_tasks
                    else "нет задач"
                )

                hot_text = (
                    "\n".join(
                        [
                            f"- {l['name']} (ID: {l['id']}, статус: {l['status']})"
                            for l in hot_leads[:10]
                        ]
                    )
                    if hot_leads
                    else "нет горячих лидов"
                )

                stale_text = (
                    "\n".join(
                        [
                            f"- {l['name']} (ID: {l['id']}), последний контакт: {str(l['updated_at'])[:10] if l['updated_at'] else 'неизвестно'}"
                            for l in stale_leads[:10]
                        ]
                    )
                    if stale_leads
                    else "нет давних контактов"
                )

                prompt = f"""Составь план рабочего дня для менеджера по продажам подшипников и комплектующих. Рабочий день 9:00-18:00.

Открытые задачи:
{tasks_text}

Горячие лиды (требуют внимания):
{hot_text}

Лиды без контакта больше 2 дней:
{stale_text}

Верни ТОЛЬКО JSON:
{{
  "greeting": "короткая мотивирующая фраза на день, 1 предложение",
  "focus": "главный приоритет дня одним предложением",
  "schedule": [
    {{
      "time": "09:00",
      "type": "call/task/kp/followup",
      "title": "что делать",
      "lead_id": null,
      "task_id": null,
      "duration_min": 15
    }}
  ],
  "calls_target": 20,
  "kp_target": 2,
  "tip": "один практический совет на сегодня"
}}

Расставь по времени с учётом приоритетов. Сначала горячие, потом задачи с дедлайном, потом холодные контакты."""

                try:
                    result = await call_claude(prompt)
                    plan = parse_ai_json(result)
                except Exception as e:
                    logger.error(f"[generate_daily_plan] Ошибка при генерации плана: {e}")
                    plan = {
                        "greeting": "Отличный день для новых сделок!",
                        "focus": "Сфокусируйся на горячих лидах",
                        "schedule": [
                            {
                                "time": "09:00",
                                "type": "call",
                                "title": "Обзвон горячих лидов",
                                "lead_id": None,
                                "task_id": None,
                                "duration_min": 60,
                            }
                        ],
                        "calls_target": 15,
                        "kp_target": 1,
                        "tip": "Начни день с самых сложных звонков",
                    }

                await conn.execute(
                    """
                    INSERT INTO daily_plans (user_id, date, plan_data, updated_at)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (user_id, date)
                    DO UPDATE SET plan_data = EXCLUDED.plan_data, updated_at = EXCLUDED.updated_at
                    """,
                    user_id,
                    today_date,
                    json.dumps(plan, ensure_ascii=False),
                    now,
                )

                return plan
        else:
            # Случай: db_conn передан снаружи
            open_tasks = await conn.fetch(
                """
                SELECT id, title, priority, due_date
                FROM tasks
                WHERE assigned_to = $1 AND status != 'done'
                ORDER BY CASE priority
                    WHEN 'urgent' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'normal' THEN 3
                    ELSE 4
                END, due_date ASC
                """,
                user_id,
            )

            hot_statuses = ["новый", "горячий", "в_работе"]
            hot_leads = await conn.fetch(
                """
                SELECT id, name, status
                FROM parsed_leads
                WHERE assigned_to = $1 AND status = ANY($2::text[])
                """,
                user_id,
                hot_statuses,
            )

            stale_dt_param = str((datetime.now() - timedelta(days=2)).isoformat())
            stale_leads = await conn.fetch(
                """
                SELECT id, name, updated_at
                FROM parsed_leads
                WHERE assigned_to = $1
                  AND status NOT IN ('закрыт', 'отказ')
                  AND updated_at < $2
                ORDER BY updated_at ASC
                LIMIT 10
                """,
                user_id,
                stale_dt_param,
            )

            tasks_text = (
                "\n".join(
                    [
                        f"- [{t['priority']}] {t['title']}, дедлайн: {str(t['due_date'])[:10] if t['due_date'] else 'нет'}"
                        for t in open_tasks[:15]
                    ]
                )
                if open_tasks
                else "нет задач"
            )

            hot_text = (
                "\n".join(
                    [
                        f"- {l['name']} (ID: {l['id']}, статус: {l['status']})"
                        for l in hot_leads[:10]
                    ]
                )
                if hot_leads
                else "нет горячих лидов"
            )

            stale_text = (
                "\n".join(
                    [
                        f"- {l['name']} (ID: {l['id']}), последний контакт: {str(l['updated_at'])[:10] if l['updated_at'] else 'неизвестно'}"
                        for l in stale_leads[:10]
                    ]
                )
                if stale_leads
                else "нет давних контактов"
            )

            prompt = f"""Составь план рабочего дня для менеджера по продажам подшипников и комплектующих. Рабочий день 9:00-18:00.

Открытые задачи:
{tasks_text}

Горячие лиды (требуют внимания):
{hot_text}

Лиды без контакта больше 2 дней:
{stale_text}

Верни ТОЛЬКО JSON:
{{
  "greeting": "короткая мотивирующая фраза на день, 1 предложение",
  "focus": "главный приоритет дня одним предложением",
  "schedule": [
    {{
      "time": "09:00",
      "type": "call/task/kp/followup",
      "title": "что делать",
      "lead_id": null,
      "task_id": null,
      "duration_min": 15
    }}
  ],
  "calls_target": 20,
  "kp_target": 2,
  "tip": "один практический совет на сегодня"
}}

Расставь по времени с учётом приоритетов. Сначала горячие, потом задачи с дедлайном, потом холодные контакты."""

            try:
                result = await call_claude(prompt)
                plan = parse_ai_json(result)
            except Exception as e:
                logger.error(f"[generate_daily_plan] Ошибка при генерации плана: {e}")
                plan = {
                    "greeting": "Отличный день для новых сделок!",
                    "focus": "Сфокусируйся на горячих лидах",
                    "schedule": [
                        {
                            "time": "09:00",
                            "type": "call",
                            "title": "Обзвон горячих лидов",
                            "lead_id": None,
                            "task_id": None,
                            "duration_min": 60,
                        }
                    ],
                    "calls_target": 15,
                    "kp_target": 1,
                    "tip": "Начни день с самых сложных звонков",
                }

            await conn.execute(
                """
                INSERT INTO daily_plans (user_id, date, plan_data, updated_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, date)
                DO UPDATE SET plan_data = EXCLUDED.plan_data, updated_at = EXCLUDED.updated_at
                """,
                user_id,
                today_date,
                json.dumps(plan, ensure_ascii=False),
                now,
            )
            return plan
    finally:
        pass


def get_daily_plan_for_team_or_user(current_user: dict[str, Any]) -> list[dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now()
    month = now.month
    year = now.year
    today_str = now.strftime("%Y-%m-%d")

    # DISABLED_FOR_PRESENTATION — always all employees (was role-based filter)
    cursor.execute(q("SELECT id, name FROM users WHERE role = 'employee' ORDER BY name"))
    users = cursor.fetchall()

    result: list[dict[str, Any]] = []
    for uid, uname in users:
        cursor.execute(
            q(
                """
                SELECT calls_target, registrations_target FROM employee_plans
                WHERE user_id = %s AND month = %s AND year = %s
            """
            ),
            (uid, month, year),
        )
        plan_row = cursor.fetchone()
        calls_target = plan_row[0] if plan_row else 0
        regs_target = plan_row[1] if plan_row else 0

        # Рабочие дни примерно 22 в месяц
        work_days = 22
        daily_calls = round(calls_target / work_days) if calls_target else 0

        # Сколько звонков сделано сегодня
        cursor.execute(
            q(
                """
                SELECT COUNT(*) FROM call_logs
                WHERE user_id = %s AND call_date = %s AND status = 'completed'
            """
            ),
            (uid, today_str),
        )
        completed_today = cursor.fetchone()[0]

        # Сколько лидов назначено
        cursor.execute(
            q(
                """
                SELECT COUNT(*) FROM parsed_leads WHERE assigned_to = %s AND status != 'закрыт'
            """
            ),
            (uid,),
        )
        assigned_leads = cursor.fetchone()[0]

        result.append(
            {
                "user_id": uid,
                "user_name": uname,
                "calls_target": calls_target,
                "registrations_target": regs_target,
                "daily_calls": daily_calls,
                "completed_today": completed_today,
                "assigned_leads": assigned_leads,
                "remaining_calls": max(0, daily_calls - completed_today),
            }
        )

    conn.close()
    return result


def generate_daily_plan_assign_unassigned_leads(current_user: dict[str, Any]) -> dict[str, Any]:
    # DISABLED_FOR_PRESENTATION — role check removed

    conn = get_db()
    cursor = conn.cursor()

    # Получить всех менеджеров
    cursor.execute(q("SELECT id, name FROM users WHERE role = 'employee' ORDER BY name"))
    employees = cursor.fetchall()
    if not employees:
        conn.close()
        return {"detail": "No employees found"}

    # Получить все нераспределенные лиды
    cursor.execute(
        q(
            """
            SELECT id FROM parsed_leads
            WHERE assigned_to IS NULL AND status = 'новый' ORDER BY created_at DESC
        """
        )
    )
    unassigned = [r[0] for r in cursor.fetchall()]

    now = datetime.now().isoformat()
    assigned_count = 0
    for i, lead_id in enumerate(unassigned):
        emp_id = employees[i % len(employees)][0]
        cursor.execute(
            q(
                """
                UPDATE parsed_leads SET assigned_to = %s, updated_at = %s WHERE id = %s
            """
            ),
            (emp_id, now, lead_id),
        )
        assigned_count += 1

    conn.commit()
    conn.close()
    return {"detail": f"Assigned {assigned_count} leads to {len(employees)} employees"}
