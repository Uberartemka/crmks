from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from fastapi import FastAPI

logger = logging.getLogger("HHB_B2B")

# ---- Rate limit config ----
WINDOW_SECONDS = 60

# ---- In-memory store (no Redis dependency) ----
# key: ip:path -> list of timestamps
_store: Dict[str, List[float]] = defaultdict(list)


def _get_rate_limit(path: str) -> int:
    if "/api/ai/search" in path:
        return 10
    if "/api/queue/add" in path:
        return 20
    if "/api/webhooks/" in path:
        return 30
    return 60


def _extract_client_ip(request: Request) -> str:
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()

    x_real_ip = request.headers.get("X-Real-IP")
    if x_real_ip:
        return x_real_ip.strip()

    return request.client.host if request.client else "unknown"


def _check_rate_limit(key: str, limit: int) -> Tuple[bool, int]:
    """Returns (is_blocked, current_count)."""
    now = time.time()
    window_start = now - WINDOW_SECONDS

    timestamps = _store[key]
    # Filter out old entries
    timestamps[:] = [t for t in timestamps if t > window_start]

    if len(timestamps) >= limit:
        return True, len(timestamps)

    timestamps.append(now)
    return False, len(timestamps) + 1


def register_rate_limiter(app: FastAPI) -> None:
    @app.middleware("http")
    async def rate_limiting_middleware(request: Request, call_next):
        path = request.url.path
        if path in ["/", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)

        limit = _get_rate_limit(path)
        client_ip = _extract_client_ip(request)
        key = f"{client_ip}:{path}"

        try:
            is_blocked, current = _check_rate_limit(key, limit)

            if is_blocked:
                logger.warning(
                    f"[Rate Limit Blocked] IP {client_ip} превысил лимит на {path} ({limit} запр./мин). current={current}"
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Too Many Requests. Вы превысили лимит запросов для этого эндпоинта. Попробуйте позже."
                    },
                    headers={"Retry-After": str(WINDOW_SECONDS)},
                )

        except Exception as e:
            logger.error(f"[RateLimiter] Error: {e}")
            return await call_next(request)

        return await call_next(request)
