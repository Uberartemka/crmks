from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from db import get_db, q
from routes.ai_claude_agent import call_claude, JSON_SYSTEM_PROMPT
from utils.ai_utils import parse_ai_json

logger = logging.getLogger("HHB_B2B")


async def run_nightly_agent() -> None:
    """Ночной AI-обход “залежалых” лидов — планировщик (23:00)."""
    logger.info("[Scheduler] Запуск фонового ночного обхода ИИ...")
    from db_async import get_async_pool

    try:
        pool = await get_async_pool()

        stale_date = (datetime.now() - timedelta(days=3)).isoformat()

        async with pool.acquire() as conn:
            stale_rows = await conn.fetch(
                """
                SELECT id, name, status, assigned_to
                FROM parsed_leads
                WHERE status NOT IN ('закрыт', 'отказ')
                  AND updated_at < $1
                """,
                stale_date,
            )

            for row in stale_rows:
                lead_id = row["id"]
                company_name = row["name"]
                lead_status = row["status"]
                assigned_to = row["assigned_to"]

                # Проверяем нет ли открытой задачи
                existing = await conn.fetchrow(
                    """
                    SELECT id
                    FROM tasks
                    WHERE lead_id = $1 AND status = 'todo'
                    LIMIT 1
                    """,
                    lead_id,
                )
                if existing:
                    continue

                last_call_row = await conn.fetchrow(
                    """
                    SELECT created_at, status, notes
                    FROM call_logs
                    WHERE lead_id = $1
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    lead_id,
                )

                if last_call_row and last_call_row["created_at"]:
                    # created_at может быть datetime — приводим к строке с датой
                    last_call_date = str(last_call_row["created_at"])[:10]
                else:
                    last_call_date = "не было"

                last_call_status = last_call_row["status"] if last_call_row else "нет"
                last_call_notes = last_call_row["notes"] if last_call_row else "нет"

                prompt = f"""Ты агент CRM. Клиент давно без контакта — нужно ли что-то сделать?

Клиент: {company_name}
Статус лида: {lead_status}
Последний звонок: {last_call_date}
Последний статус звонка: {last_call_status}
Заметки: {last_call_notes}

Верни ТОЛЬКО JSON:
{{
  "needs_task": true/false,
  "title": "название задачи",
  "description": "что сделать",
  "priority": "low/normal/high",
  "due_hours": 24
}}"""

                try:
                    result = await call_claude(prompt, system=JSON_SYSTEM_PROMPT)
                    data: dict[str, Any] = parse_ai_json(result)
                except Exception as e:
                    logger.error(f"[Scheduler] AI error for lead_id={lead_id}: {e}")
                    continue

                if not data.get("needs_task"):
                    continue

                due = (datetime.now() + timedelta(hours=data.get("due_hours", 48))).isoformat()
                now = datetime.now().isoformat()

                await conn.execute(
                    """
                    INSERT INTO tasks (
                        assigned_to, created_by, lead_id, title, description,
                        priority, due_date, status, source, created_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """,
                    assigned_to,
                    "ai_agent",
                    lead_id,
                    data["title"],
                    data["description"],
                    data["priority"],
                    due,
                    "todo",
                    "weekly_review",
                    now,
                )

        logger.info("[Scheduler] Фоновый ночной обход ИИ выполнен успешно.")
    except Exception as e:
        logger.error(f"[Scheduler Error] Ошибка фонового ночного обхода ИИ: {e}")
