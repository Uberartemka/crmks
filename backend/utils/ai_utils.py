from __future__ import annotations

import asyncio
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

logger = logging.getLogger("HHB_B2B")

try:
    import kimi_client
except Exception as e:  # pragma: no cover
    kimi_client = None
    logger.warning(f"[KIMI] kimi_client отключён: {e}")

KIMI_TIMEOUT_SEC: float = float(os.getenv("KIMI_TIMEOUT_SEC", "25"))
KIMI_MAX_WORKERS: int = int(os.getenv("KIMI_MAX_WORKERS", "8"))

_kimi_executor = ThreadPoolExecutor(
    max_workers=KIMI_MAX_WORKERS,
    thread_name_prefix="kimi",
)

web_search_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="websearch")


async def call_kimi_async(
    prompt: str,
    temperature: float = 0.3,
    timeout: float = KIMI_TIMEOUT_SEC,
) -> str:
    """
    Async wrapper для вызова Kimi (Moonshot) через ThreadPoolExecutor.

    ВАЖНО: добавлен timeout, чтобы не "заклинивать" пул потоков навечно,
    если Kimi начинает отвечать слишком долго.
    """
    if not kimi_client:
        raise RuntimeError("kimi_client не доступен")

    messages = [{"role": "user", "content": prompt}]

    loop = asyncio.get_running_loop()

    def _call() -> str:
        choice = kimi_client.chat_completion(messages, temperature=temperature)
        return choice.message.content or ""

    try:
        # asyncio.wait_for отменяет ожидание, но underlying thread продолжит работу.
        # При этом event loop не зависает, и мы можем корректно fallback/возвращать ошибку.
        return await asyncio.wait_for(loop.run_in_executor(_kimi_executor, _call), timeout=timeout)
    except asyncio.TimeoutError:
        logger.error(f"[call_kimi_async] Таймаут {timeout}s")
        raise RuntimeError(f"Kimi не ответил за {timeout} секунд")
    except Exception as e:
        logger.error(f"[call_kimi_async] Ошибка: {e}")
        raise


def parse_ai_json(result: str) -> Any:
    """
    Унифицированный парсер JSON-ответа LLM.

    Поддерживает формат:
      - plain JSON
      - ```json ... ```
      - ``` ... ```
    """
    if result is None:
        raise ValueError("AI result is None")

    clean = (
        result.strip()
        .lstrip("```json")
        .lstrip("```")
        .rstrip("```")
        .strip()
    )
    return json.loads(clean)
