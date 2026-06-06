from __future__ import annotations

import json
import os
import time
import traceback
import urllib.request
from typing import Optional

import logging
from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger("HHB_B2B")

router = APIRouter(prefix="/api/ai", tags=["ai"])


class AiSearchRequest(BaseModel):
    query: str = Field(..., description="Поисковый запрос")
    api_key: Optional[str] = None


def get_local_fallback_response(query: str) -> dict:
    query_lower = query.lower()
    if any(k in query_lower for k in ["6205", "skf", "фаг", "fag"]):
        return {
            "title": "HHB 6205-2RS C3 Premium",
            "desc": "Премиальный шариковый радиальный подшипник HHB (аналог SKF 6205-2RS1). Снабжен двусторонним износостойким уплотнением из каучука для удержания смазки и радиальным зазором C3 для бесперебойной работы при температуре до +120°C.",
            "price": "420 ₽",
            "stock": "1 240 шт",
            "cross": "SKF 6205-2RS1/C3, FAG 6205-2RSR-C3",
        }
    if any(k in query_lower for k in ["нори", "вал 30", "пыл", "uc"]):
        return {
            "title": "HHB UCP 206 (корпусной узел на лапах)",
            "desc": "Профессиональный подшипниковый узел (чугунный литой корпус UCP206 + радиальный подшипник UC206). Оснащен трехкромочным уплотнением LS3, исключающим попадание мелкодисперсной зерновой пыли нории внутрь узла. Заполнен высококачественной агропылевой смазкой.",
            "price": "1 180 ₽",
            "stock": "86 комплектов",
            "cross": "FKL UCP206, SKF SY 30 TF",
        }

    return {
        "title": "HHB UCF 208 (фланцевый квадратный узел)",
        "desc": "Высоконадежный фланцевый узел (четырехболтовый квадратный корпус F208 + подшипник UC208). Рассчитан на высокие статические и динамические радиальные нагрузки. Посадочный вал 40 мм. Подходит для приводов элеваторов и тяжелых сеялок.",
        "price": "1 420 ₽",
        "stock": "140 шт",
        "cross": "FKL UCF208, SKF FY 40 TF",
    }


@router.post("/search")
def ai_search(payload: AiSearchRequest):
    query = payload.query.strip()
    logger.info(f"[AI Search] Получен новый поисковый запрос: '{query}'")

    start_time = time.time()

    api_key = payload.api_key or os.getenv("DEEPSEEK_API_KEY")

    if api_key:
        try:
            logger.info("[AI Search] Отправка запроса к официальному API DeepSeek...")

            req = urllib.request.Request(
                "https://api.deepseek.com/chat/completions",
                data=json.dumps(
                    {
                        "model": "deepseek-chat",
                        "messages": [
                            {
                                "role": "system",
                                "content": "Ты профессиональный консультант ООО Компонент Сервис, эксперт по премиум-подшипникам HHB и FKD. Выдай строго JSON с полями title, desc, price, stock, cross.",
                            },
                            {"role": "user", "content": query},
                        ],
                        "temperature": 0.2,
                        "response_format": {"type": "json_object"},
                    }
                ).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )

            with urllib.request.urlopen(req, timeout=12) as response:
                resp_data = json.loads(response.read().decode("utf-8"))

            elapsed_time = time.time() - start_time
            logger.info(f"[AI Search] Успешный ответ от DeepSeek за {elapsed_time:.2f} сек.")

            return json.loads(resp_data["choices"][0]["message"]["content"])
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(
                f"[!] [AI Search Error] Сбой при запросе к DeepSeek API через {elapsed_time:.2f} сек. Ошибка: {e}"
            )
            logger.error(traceback.format_exc())
            logger.warning("[AI Search] Активирован локальный резервный офлайн-режим для бесперебойной работы фронтенда.")

    logger.info("[AI Search] Использование встроенного офлайн-генератора решений HHB/FKD.")
    time.sleep(1.2)
    return get_local_fallback_response(query)


# Legacy alias (kept for backwards compatibility with old frontend/tests)
@router.post("/search_legacy")
def ai_search_legacy(payload: AiSearchRequest):
    return ai_search(payload)
