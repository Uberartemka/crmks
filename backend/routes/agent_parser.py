import logging
import json
import traceback
import urllib.parse
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from db import _use_pg, get_db, q
from auth_deps import get_current_user

from routes.ai_claude_agent import call_claude, JSON_SYSTEM_PROMPT
from utils.ai_utils import parse_ai_json

logger = logging.getLogger("HHB_B2B")

router = APIRouter(prefix="", tags=["ai"])


class AgentParseLeadsRequest(BaseModel):
    query: str = Field(..., description="Поисковый запрос, например 'подшипники оптом Воронеж'")
    source: str = Field(default="2gis", description="Источник: 2gis, yandex_maps, avito")
    limit: int = Field(default=20, ge=1, le=100)


# Playwright import (lazy, with graceful fallback)
try:
    from playwright.async_api import async_playwright

    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False
    async_playwright = None


async def scrape_companies(query: str, source: str, limit: int) -> list:
    """
    Парсит компании из внешних источников (2gis, yandex_maps).
    Требует: pip install playwright && playwright install chromium
    """
    if not _PLAYWRIGHT_AVAILABLE:
        logger.error(
            "[scrape_companies] Playwright не установлен. Установите: pip install playwright && playwright install chromium"
        )
        raise HTTPException(
            status_code=501,
            detail="Playwright не установлен. Установите: pip install playwright && playwright install chromium",
        )

    companies: list[dict] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        if source == "2gis":
            try:
                url = f"https://2gis.ru/search/{urllib.parse.quote(query)}"
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(3000)

                # Try multiple selectors for 2gis
                selectors = [
                    "[class*='_1k5so']",  # mini card
                    "[class*='_zjunba']",  # search result
                    "[data-marker='item']",
                    "._1k5so",
                ]
                items = []
                for sel in selectors:
                    try:
                        items = await page.query_selector_all(sel)
                        if items:
                            break
                    except Exception:
                        continue

                for item in items[:limit]:
                    try:
                        name_el = await item.query_selector(
                            "[class*='_1h3cgic'], [class*='name'], h3, a"
                        )
                        name = await name_el.inner_text() if name_el else ""

                        phone_el = await item.query_selector(
                            "[class*='_b0ke6'], [class*='phone'], a[href^='tel:']"
                        )
                        phone = await phone_el.inner_text() if phone_el else ""
                        if not phone:
                            href = await phone_el.get_attribute("href") if phone_el else None
                            if href and href.startswith("tel:"):
                                phone = href.replace("tel:", "")

                        addr_el = await item.query_selector(
                            "[class*='_er2n9w'], [class*='address'], span[class*='_']"
                        )
                        address = await addr_el.inner_text() if addr_el else ""

                        if name and len(name) > 2:
                            companies.append(
                                {
                                    "name": name.strip(),
                                    "phone": phone.strip(),
                                    "address": address.strip(),
                                    "website": "",
                                }
                            )
                    except Exception as ex:
                        logger.debug(f"[scrape_companies] Ошибка при парсинге элемента: {ex}")
                        continue
            except Exception as e:
                logger.error(f"[scrape_companies] Ошибка при парсинге 2gis: {e}")

        await browser.close()

    return [c for c in companies if c.get("name")]


async def score_company(company: dict) -> dict:
    """
    AI оценка компании — стоит ли добавлять в CRM как лида.
    Использует call_claude (Claude -> Kimi fallback).
    """
    prompt = f"""Оцени компанию как потенциального клиента для дистрибьютора подшипников и комплектующих.

Компания: {company['name']}
Адрес: {company.get('address', 'нет')}
Телефон: {company.get('phone', 'нет')}

Верни ТОЛЬКО JSON:
{{
  "add": true/false,
  "potential": "high/medium/low",
  "reason": "одно предложение почему"
}}

Добавляй если: завод, производство, сервис техники, агро, строительство, транспорт, промышленность.
Не добавляй если: магазин бытовой техники, ресторан, парикмахерская, IT компания."""

    try:
        result = await call_claude(prompt, system=JSON_SYSTEM_PROMPT)
        return parse_ai_json(result)
    except Exception as e:
        logger.error(f"[score_company] Ошибка при оценке компании: {e}")
        # Default: add with medium potential if AI fails
        return {"add": True, "potential": "medium", "reason": "AI не смог оценить, добавляем на проверку"}


@router.post("/api/agent/parse-leads")
async def parse_leads_endpoint(
    body: AgentParseLeadsRequest, request: Request, current_user: dict = Depends(get_current_user)
):
    """
    Agent-парсер: сам находит потенциальных клиентов через внешние источники (2gis).
    AI оценивает каждую компанию и добавляет worthy leads в CRM.
    """
    if current_user["role"] not in ["admin", "manager"]:
        raise HTTPException(403, "Forbidden: только admin и manager могут запускать парсер")

    if not _PLAYWRIGHT_AVAILABLE:
        raise HTTPException(
            500,
            "Playwright не установлен. Установите: pip install playwright && playwright install chromium",
        )

    logger.info(
        f"[parse_leads] Запуск парсера: source={body.source}, query={body.query}, limit={body.limit}"
    )

    try:
        companies = await scrape_companies(body.query, body.source, body.limit)
    except Exception as e:
        logger.error(f"[parse_leads] scrape_companies exception: {e}")
        logger.error(traceback.format_exc())
        companies = []

    if not companies:
        # MVP fallback: если внешние источники недоступны/не распарсились — создаём лид-заглушку
        now = datetime.now().isoformat()
        placeholder_name = (body.query or "").strip()[:300] or "Лид по запросу"

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            q(
                """
                INSERT INTO parsed_leads (name, category, city, contacts, need_description, query, region, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """
            ),
            (
                placeholder_name,
                None,
                None,
                None,
                None,
                body.query,
                None,
                now,
                now,
            ),
        )
        row = cursor.fetchone()
        lead_id = row[0] if row else None
        conn.commit()
        conn.close()

        leads = []
        if lead_id:
            leads = [
                {
                    "id": lead_id,
                    "name": placeholder_name,
                    "category": None,
                    "city": None,
                    "contacts": None,
                    "need_description": None,
                    "query": body.query,
                    "region": None,
                    "status": "новый",
                }
            ]

        return {
            "parsed": 1,
            "created": len(leads),
            "skipped": 0,
            "leads": leads,
            "message": "Компании не найдены внешним парсером. Создан лид-заглушка в БД по введённому запросу (MVP).",
        }

    created: list[dict] = []
    skipped: list[dict] = []

    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    for company in companies:
        company_name: Optional[str] = company.get("name") if isinstance(company, dict) else None
        if not company_name:
            skipped.append({"name": "?", "reason": "у компании нет name"})
            continue

        # Проверяем нет ли уже в базе по названию
        name_like = f"%{company_name[:30]}%"
        if _use_pg:
            cursor.execute(
                "SELECT id FROM parsed_leads WHERE name ILIKE %s LIMIT 1", (name_like,)
            )
        else:
            cursor.execute(
                "SELECT id FROM parsed_leads WHERE name LIKE ? LIMIT 1", (name_like,)
            )

        existing = cursor.fetchone()
        if existing:
            skipped.append({"name": company_name, "reason": "уже в базе"})
            continue

        # AI оценка
        try:
            score = await score_company(company)
        except Exception as e:
            logger.error(f"[parse_leads] score_company failed: {e}")
            logger.error(traceback.format_exc())
            skipped.append(
                {"name": company.get("name", "?"), "reason": "ошибка score_company"}
            )
            continue

        if not isinstance(score, dict):
            skipped.append(
                {"name": company_name or "?", "reason": "score_company returned non-dict"}
            )
            continue

        if not score.get("add", True):
            skipped.append(
                {"name": company_name or "?", "reason": score.get("reason", "не подходит")}
            )
            continue

        # Формируем контакты: телефон + сайт (если есть)
        contacts_parts: list[str] = []
        if company.get("phone"):
            contacts_parts.append(company["phone"])
        if company.get("website"):
            contacts_parts.append(company["website"])
        contacts = " · ".join(contacts_parts) if contacts_parts else ""

        notes = (
            f"AI оценка: {score.get('reason', '')}. Потенциал: {score.get('potential', 'medium')}"
        )
        try:
            cursor.execute(
                q(
                    """
                    INSERT INTO parsed_leads (name, category, city, contacts, need_description, query, region, status, assigned_to, call_count, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                    """
                ),
                (
                    company_name[:300],
                    None,  # category
                    company.get("address", "")[:100],
                    contacts,
                    notes,
                    body.query[:200],
                    None,  # region
                    "новый",
                    None,  # assigned_to
                    0,  # call_count
                    now,
                    now,
                ),
            )

            row = cursor.fetchone()
            lead_id = row[0] if _use_pg else cursor.lastrowid
        except Exception as e:
            logger.error(
                f"[parse_leads] INSERT parsed_leads failed for '{company_name}': {e}"
            )
            logger.error(traceback.format_exc())
            skipped.append({"name": company_name or "?", "reason": "db insert failed"})
            continue

        created.append(
            {
                "id": lead_id,
                "name": company["name"],
                "potential": score.get("potential", "medium"),
                "reason": score.get("reason", ""),
            }
        )

    conn.commit()
    conn.close()

    logger.info(
        f"[parse_leads] Создано {len(created)} лидов, пропущено {len(skipped)}"
    )
    return {
        "parsed": len(companies),
        "created": len(created),
        "skipped": len(skipped),
        "leads": created,
    }
