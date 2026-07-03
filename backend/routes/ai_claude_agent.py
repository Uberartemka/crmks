import logging
import json
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from db import _use_pg, get_db, q
from auth_deps import get_current_user
from services.legacy_tasks_notes import find_best_assignee_for_task
from utils.ai_utils import parse_ai_json

logger = logging.getLogger("HHB_B2B")

router = APIRouter(prefix="", tags=["ai"])


# =========================
# Claude call + prompts
# =========================

AGENT_SYSTEM_PROMPT = """Ты быстрый CRM-ассистент для менеджеров по продажам.

ГЛАВНОЕ ПРАВИЛО: никогда не задавай уточняющих вопросов.
Вместо этого — предлагай 2-3 готовых варианта действий.

Плохо:  "Уточните, какой срок доставки указать в КП?"
Хорошо: Предложи варианты: ["3-5 рабочих дней", "7-10 рабочих дней", "уточнить у клиента"]

Плохо:  "Вы хотите создать задачу или просто записать?"
Хорошо: Создай задачу сам с приоритетом normal, верни результат.

Принципы:
- Действуй немедленно на основе контекста
- Если есть неопределённость — выбери наиболее вероятный вариант сам
- Предлагай варианты только когда решение критично и цена ошибки высока
- Отвечай кратко: максимум 3 предложения или JSON
- Никакой воды, никаких "конечно!", "отличный вопрос!", "я помогу вам"
"""


async def call_claude(prompt: str, system: str = AGENT_SYSTEM_PROMPT) -> str:
    """
    Отправляет запрос в Claude (Anthropic).
    Если ключ Anthropic не задан или запрос падает, автоматически переключается на Kimi (Cloudflare) как резервный вариант.
    """
    import httpx

    logger_local = logging.getLogger("HHB_B2B")

    call_timeout_sec = float(os.getenv("AI_CALL_TIMEOUT_SEC", "30"))

    anthropic_key = os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY")
    if anthropic_key:
        try:
            logger_local.info("[call_claude] Отправка запроса в Anthropic Claude...")
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": anthropic_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-3-5-sonnet-20241022",
                        "max_tokens": 500,
                        "system": system,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                    timeout=call_timeout_sec,
                )
                r.raise_for_status()
                data = r.json()
                result = data["content"][0]["text"]
                logger_local.info("[call_claude] Успешный ответ от Claude.")
                return result
        except Exception as e:
            logger_local.warning(
                f"[call_claude] Ошибка при запросе к Claude: {e}. Пробуем Kimi через Cloudflare..."
            )

    logger_local.info("[call_claude] Использование Kimi (Moonshot) через Cloudflare...")
    cf_account_id = os.getenv("CF_ACCOUNT_ID") or os.getenv("CLOUDFLARE_ACCOUNT_ID")
    cf_token = os.getenv("CF_API_TOKEN") or os.getenv("CLOUDFLARE_API_TOKEN")
    cf_model = os.getenv("CF_MODEL") or "@cf/moonshotai/kimi-k2.5"

    if cf_account_id and cf_token:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    f"https://api.cloudflare.com/client/v4/accounts/{cf_account_id}/ai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {cf_token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": cf_model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.2,
                    },
                    timeout=call_timeout_sec,
                )
                r.raise_for_status()
                data = r.json()
                if "result" in data and "response" in data["result"]:
                    result = data["result"]["response"]
                else:
                    result = data["choices"][0]["message"]["content"]
                logger_local.info("[call_claude] Успешный ответ от Kimi.")
                return result
        except Exception as ex:
            logger_local.error(f"[call_claude] Ошибка при запросе к Kimi: {ex}")
            raise HTTPException(
                500, f"Ошибка ИИ: не удалось получить ответ ни от Claude, ни от Kimi. Детали: {ex}"
            )

    raise HTTPException(
        500, "Ошибка ИИ: не настроены ключи ни для Anthropic (ANTHROPIC_AUTH_TOKEN), ни для Cloudflare (CF_API_TOKEN)."
    )


# =========================
# AI endpoints
# =========================

@router.post("/api/calls/{call_id}/analyze")
async def analyze_call(call_id: int, request: Request):
    current_user = get_current_user(request)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(q("SELECT notes, transcript, user_id FROM call_logs WHERE id = %s"), (call_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Звонок не найден")

    notes, transcript, _user_id = row
    text_to_analyze = transcript or notes or ""
    if not text_to_analyze:
        conn.close()
        raise HTTPException(400, "Нет текста звонка или заметок для анализа")

    prompt = f"""Ты супервайзер отдела продаж. Оцени звонок менеджера по 5 критериям.
Верни ТОЛЬКО JSON без пояснений:

{{
  "score": 0-100,
  "greeting": true/false,
  "identified_need": true/false,
  "handled_objections": true/false,
  "proposed_solution": true/false,
  "closed_next_step": true/false,
  "weak_points": ["список слабых мест"],
  "recommendation": "одна конкретная рекомендация менеджеру"
}}

Текст звонка / заметки:
{text_to_analyze}"""

    response = await call_claude(prompt)
    result = parse_ai_json(response)

    score = result.get("score", 0)
    cursor.execute(
        q("""
        UPDATE call_logs
        SET ai_score = %s, ai_analysis = %s
        WHERE id = %s
        """),
        (score, json.dumps(result, ensure_ascii=False), call_id),
    )

    conn.commit()
    conn.close()
    return result


@router.get("/api/leads/{lead_id}/briefing")
async def lead_briefing(lead_id: int, request: Request):
    _current_user = get_current_user(request)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        q("SELECT name, contacts, need_description FROM parsed_leads WHERE id = %s"), (lead_id,)
    )
    lead_row = cursor.fetchone()
    if not lead_row:
        conn.close()
        raise HTTPException(404, "Лид не найден")

    company_name, contacts, need_desc = lead_row

    cursor.execute(
        q("""
        SELECT created_at, status, notes
        FROM call_logs
        WHERE lead_id = %s
        ORDER BY created_at DESC
        LIMIT 5
        """),
        (lead_id,),
    )
    calls_rows = cursor.fetchall()

    calls_text = "\n".join(
        [f"- {r[0][:10] if r[0] else 'Дата неизвестна'}: {r[1]}, {r[2] or 'без заметок'}" for r in calls_rows]
    ) if calls_rows else "Звонков ещё не было"

    prompt = f"""Ты помощник менеджера по продажам подшипников.
Подготовь короткую шпаргалку перед звонком клиенту.

Клиент: {company_name}
Контакты / инфо: {contacts or 'нет'}
Описание потребности: {need_desc or 'нет'}
История звонков:
{calls_text}

Верни JSON:
{{
  "reminder": "что важно помнить про этого клиента",
  "talking_points": ["3 темы для разговора"],
  "avoid": "чего избегать в разговоре",
  "goal": "цель этого звонка одним предложением"
}}

Только JSON."""

    result = await call_claude(prompt)
    conn.close()
    return parse_ai_json(result)


class ParseKpRequest(BaseModel):
    text: str


@router.post("/api/kp/parse-request")
async def parse_kp_request(body: Dict[str, Any], request: Request):
    _current_user = get_current_user(request)

    client_text = body.get("text", "")
    if not client_text:
        raise HTTPException(400, "Текст запроса пустой")

    prompt = f"""Ты помощник менеджера по продажам комплектующих.
Из текста запроса клиента извлеки список позиций для КП.

Текст: "{client_text}"

Верни ТОЛЬКО JSON массив:
[
  {{
    "article": "артикул или описание",
    "qty": число или null если не указано,
    "brand": "бренд если указан или null",
    "note": "срочно / аналог / уточнить — если есть"
  }}
]

Если артикул не распознан — пиши его как есть в поле article.
Только JSON, без пояснений."""

    result = await call_claude(prompt)
    items = parse_ai_json(result)

    conn = get_db()
    cursor = conn.cursor()

    enriched = []
    for item in items:
        article = item.get("article", "")
        cursor.execute(
            q("SELECT id, code, price_new FROM products WHERE code ILIKE %s LIMIT 1"),
            (f"%{article}%",),
        )
        cat_row = cursor.fetchone()

        enriched.append(
            {
                **item,
                "found_in_catalog": cat_row is not None,
                "catalog_id": cat_row[0] if cat_row else None,
                "price": float(cat_row[2]) if cat_row and cat_row[2] else None,
                "name": cat_row[1] if cat_row else None,
            }
        )

    conn.close()
    return {"items": enriched}


@router.get("/api/reports/weekly-summary")
async def weekly_summary(request: Request):
    _current_user = get_current_user(request)

    from datetime import datetime, timedelta
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        q("""
        SELECT user_id, status
        FROM call_logs
        WHERE created_at >= %s
        """),
        (week_ago,),
    )
    calls_rows = cursor.fetchall()

    total = len(calls_rows)
    reached = len([r for r in calls_rows if r[1] in ("completed", "дозвонился")])
    refused = len([r for r in calls_rows if r[1] in ("отказ", "refused")])

    from collections import defaultdict
    by_manager = defaultdict(lambda: {"total": 0, "reached": 0})
    for r in calls_rows:
        uid, status = r
        if uid is not None:
            by_manager[uid]["total"] += 1
            if status in ("completed", "дозвонился"):
                by_manager[uid]["reached"] += 1

    cursor.execute(q("SELECT id, name FROM users"))
    user_names = {r[0]: r[1] for r in cursor.fetchall()}

    managers_text = "\n".join(
        [
            f"- {user_names.get(uid, f'ID {uid}')}: {v['total']} звонков, {v['reached']} дозвонов"
            for uid, v in by_manager.items()
        ]
    )

    prompt = f"""Ты бизнес-аналитик. Напиши короткий еженедельный отчёт 
для директора компании по продаже подшипников и комплектующих.
Пиши по-русски, деловой но простой язык, без воды.

Данные за неделю:
- Всего звонков: {total}
- Дозвонов: {reached}
- Отказов: {refused}
- Конверсия дозвона: {round(reached/total*100) if total else 0}%
По менеджерам:
{managers_text}

Структура ответа:
1. Общая оценка недели (2 предложения)
2. Что хорошо
3. Что требует внимания
4. Одна конкретная рекомендация на следующую неделю

Максимум 150 слов."""

    result = await call_claude(prompt)
    conn.close()

    return {
        "report": result,
        "stats": {
            "total_calls": total,
            "reached": reached,
            "refused": refused,
            "conversion": round(reached / total * 100) if total else 0,
        },
    }


@router.post("/api/calls/{call_id}/next-action")
async def suggest_next_action(call_id: int, request: Request):
    _current_user = get_current_user(request)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(q("SELECT notes, transcript, lead_id, status FROM call_logs WHERE id = %s"), (call_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Звонок не найден")

    notes, transcript, lead_id, call_status = row

    company_name = "неизвестно"
    if lead_id:
        cursor.execute(q("SELECT name FROM parsed_leads WHERE id = %s"), (lead_id,))
        lead_row = cursor.fetchone()
        if lead_row:
            company_name = lead_row[0]

    conn.close()

    prompt = f"""Ты агент CRM системы. Звонок завершён.
Клиент: {company_name}
Статус звонка: {call_status}
Заметки менеджера: {notes or 'нет'}
Расшифровка звонка: {transcript or 'нет'}

Предложи ровно 3 варианта следующего действия.
Верни ТОЛЬКО JSON:
{{
  "options": [
    {{
      "id": 1,
      "label": "Отправить КП сегодня",
      "action": "create_kp",
      "priority": "urgent",
      "due_hours": 4
    }},
    {{
      "id": 2,
      "label": "Перезвонить завтра утром",
      "action": "create_task",
      "priority": "normal",
      "due_hours": 18
    }},
    {{
      "id": 3,
      "label": "Отложить на неделю",
      "action": "create_task",
      "priority": "low",
      "due_hours": 168
    }}
  ],
  "recommended": 1
}}

Выбери наиболее подходящее и логичное рекомендованное действие (recommended) на основе заметок и статуса звонка.
Только JSON, без пояснений."""

    result = await call_claude(prompt)
    return parse_ai_json(result)


@router.post("/api/calls/{call_id}/confirm-action")
async def confirm_action(call_id: int, body: Dict[str, Any], request: Request):
    _current_user = get_current_user(request)

    action = body.get("action")
    priority = body.get("priority", "normal")
    due_hours = body.get("due_hours", 24)
    label = body.get("label")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(q("SELECT user_id, lead_id FROM call_logs WHERE id = %s"), (call_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Звонок не найден")

    user_id, lead_id = row

    from datetime import datetime, timedelta
    due = (datetime.now() + timedelta(hours=due_hours)).isoformat()
    now = datetime.now().isoformat()

    if action == "create_task":
        cursor.execute(
            q("""
            INSERT INTO tasks (assigned_to, created_by, lead_id, call_id, title, description, priority, due_date, status, source, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """),
            (
                user_id,
                "ai_agent",
                lead_id,
                call_id,
                label,
                f"Автоматически предложенное ИИ действие: {label}",
                priority,
                due,
                "todo",
                "after_call",
                now,
            ),
        )

        if _use_pg:
            cursor.execute("SELECT LASTVAL()")
        else:
            cursor.execute("SELECT last_insert_rowid()")
        new_id = cursor.fetchone()[0]

        conn.commit()
        conn.close()
        return {"ok": True, "created": "task", "task_id": new_id}

    if action == "create_kp":
        conn.close()
        return {"ok": True, "created": "kp_draft", "lead_id": lead_id}

    conn.close()
    return {"ok": True}


@router.post("/api/agent/nightly-review")
async def nightly_review(request: Request):
    _current_user = get_current_user(request)

    from datetime import datetime, timedelta
    stale_date = (datetime.now() - timedelta(days=3)).isoformat()

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        q("""
        SELECT id, name, status, assigned_to
        FROM parsed_leads
        WHERE status NOT IN ('закрыт', 'отказ') AND updated_at < %s
        """),
        (stale_date,),
    )
    stale_leads = cursor.fetchall()

    created_tasks = []

    for lead_id, company_name, lead_status, assigned_to in stale_leads:
        cursor.execute(
            q("SELECT id FROM tasks WHERE lead_id = %s AND status = 'todo' LIMIT 1"),
            (lead_id,),
        )
        if cursor.fetchone():
            continue

        cursor.execute(
            q("""
            SELECT created_at, status, notes
            FROM call_logs
            WHERE lead_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """),
            (lead_id,),
        )
        last_call_row = cursor.fetchone()

        last_call_date = last_call_row[0][:10] if last_call_row and last_call_row[0] else "не было"
        last_call_status = last_call_row[1] if last_call_row else "нет"
        last_call_notes = last_call_row[2] if last_call_row else "нет"

        prompt = f"""Ты агент CRM. Клиент давно без контакта — нужно ли
что-то сделать?

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

        result = await call_claude(prompt)
        data = parse_ai_json(result)

        if not data["needs_task"]:
            continue

        due = (datetime.now() + timedelta(hours=data.get("due_hours", 48))).isoformat()
        now = datetime.now().isoformat()

        best_assignee = find_best_assignee_for_task(data["priority"], "followup")
        assigned_to_final = best_assignee["user_id"] if best_assignee else assigned_to

        cursor.execute(
            q("""
            INSERT INTO tasks (assigned_to, created_by, lead_id, title, description, priority, due_date, status, source, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """),
            (
                assigned_to_final,
                "ai_agent",
                lead_id,
                data["title"],
                data["description"],
                data["priority"],
                due,
                "todo",
                "weekly_review",
                now,
            ),
        )

        created_tasks.append({"lead": company_name, "task": data["title"], "priority": data["priority"]})

    conn.commit()
    conn.close()

    return {
        "reviewed": len(stale_leads),
        "tasks_created": len(created_tasks),
        "tasks": created_tasks,
    }
