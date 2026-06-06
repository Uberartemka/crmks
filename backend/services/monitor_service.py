from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any

import httpx

from db import get_db, q
from routes.ai_claude_agent import call_claude
from services.legacy_tasks_notes import find_best_assignee_for_task
from utils.ai_utils import parse_ai_json

logger = logging.getLogger("HHB_B2B")


async def monitor_clients_internal() -> dict[str, Any]:
    """
    Agent-мониторинг: проверяет сайты клиентов на сигналы (тендеры, вакансии, новости).
    Создает задачи при обнаружении сигналов.
    """
    import asyncio
    from db_async import get_async_pool

    pool = await get_async_pool()

    async with pool.acquire() as conn:
        # Берём клиентов с сайтами и активными лидами
        rows = await conn.fetch(
            """
            SELECT id, name, contacts, assigned_to
            FROM parsed_leads
            WHERE contacts ILIKE '%.%' AND status NOT IN ('отказ', 'закрыт')
            """
        )

        leads = [
            (r["id"], r["name"], r["contacts"], r["assigned_to"])
            for r in rows
        ]

        # Для smoke/CI можно отключить AI-вызовы (внешние сети) и завершить быстро.
        ai_enabled = os.getenv("MONITOR_CLIENTS_AI_ENABLED", "1") == "1"
        if not ai_enabled:
            logger.info(
                f"[monitor_clients] AI disabled by env. Skipping AI checks. monitored={len(leads)}"
            )
            return {"monitored": len(leads), "signals_found": 0, "signals": []}

        signals: list[dict[str, Any]] = []
        now = datetime.now().isoformat()

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            for lead_id, company_name, contacts, assigned_to in leads:
                # Извлекаем URL из контактов (простая эвристика)
                website = None
                if contacts:
                    parts = contacts.split(" · ")
                    for part in parts:
                        if "." in part and (
                            part.startswith("http")
                            or part.startswith("www")
                            or ".ru" in part
                            or ".com" in part
                        ):
                            website = part if part.startswith("http") else f"https://{part}"
                            break

                if not website:
                    continue

                try:
                    r = await client.get(
                        website,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; HHB CRM Bot/1.0)"},
                    )
                    page_text = r.text[:4000]  # Берём первые 4000 символов
                except Exception as e:
                    logger.debug(f"[monitor_clients] Не удалось получить {website}: {e}")
                    continue

                prompt = f"""Проанализируй текст страницы сайта компании.
Найди сигналы что компании могут быть нужны подшипники или промышленные комплектующие.

Компания: {company_name}
Текст страницы:
{page_text}

Верни ТОЛЬКО JSON:
{{
  "has_signal": true/false,
  "signal_type": "tender/vacancy/news/expansion/equipment/none",
  "description": "что именно нашёл, 1-2 предложения",
  "urgency": "high/medium/low"
}}

Сигналы: тендер на закупку, вакансия механика/технолога, расширение производства, покупка оборудования, новый цех, увеличение выпуска, ремонт, модернизация."""

                try:
                    result = await call_claude(prompt)
                    data = parse_ai_json(result)
                except Exception as e:
                    logger.debug(f"[monitor_clients] Ошибка AI анализа для {company_name}: {e}")
                    continue

                if not data.get("has_signal"):
                    continue

                urgency = data.get("urgency", "medium")
                priority = "high" if urgency == "high" else ("low" if urgency == "low" else "normal")
                due = (datetime.now() + timedelta(hours=4)).isoformat()

                desc = (
                    f"Источник: {website}\n"
                    f"Сигнал: {data.get('description', '')}\n"
                    f"Тип: {data.get('signal_type', 'unknown')}"
                )
                title = f"🔔 Сигнал: {data.get('description', 'Обновление на сайте клиента')[:60]}"

                # find_best_assignee_for_task внутри дергает sync get_db/cursor.
                # Чтобы не блокировать event loop — выполняем в thread.
                best_assignee = await asyncio.to_thread(
                    find_best_assignee_for_task,
                    priority,
                    "monitoring",
                )
                assigned_to_final = best_assignee["user_id"] if best_assignee else assigned_to

                await conn.execute(
                    """
                    INSERT INTO tasks
                        (assigned_to, created_by, lead_id, title, description, priority, due_date, status, source, created_at)
                    VALUES
                        ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """,
                    assigned_to_final,
                    "ai_agent",
                    lead_id,
                    title,
                    desc,
                    priority,
                    due,
                    "todo",
                    "site_monitor",
                    now,
                )

                signals.append(
                    {
                        "company": company_name,
                        "signal": data.get("description", ""),
                        "urgency": urgency,
                    }
                )

        logger.info(
            f"[monitor_clients] Проверено {len(leads)} сайтов, найдено {len(signals)} сигналов"
        )
        return {
            "monitored": len(leads),
            "signals_found": len(signals),
            "signals": signals,
        }


async def run_site_monitor_scheduler() -> None:
    """Запуск мониторинга сайтов по расписанию."""
    try:
        result = await monitor_clients_internal()
        logger.info(
            f"[run_site_monitor] Мониторинг завершён: {result['signals_found']} сигналов из {result['monitored']} сайтов"
        )
    except Exception as e:
        logger.error(f"[run_site_monitor_scheduler] Ошибка: {e}")
