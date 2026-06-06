from __future__ import annotations

import logging
import os
import time
from typing import DefaultDict, List, Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from fastapi import FastAPI
import redis.asyncio as aioredis

logger = logging.getLogger("HHB_B2B")

# ---- Redis config ----
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
REDIS_FAIL_FAST = int(os.getenv("REDIS_FAIL_FAST", "1"))
REDIS_INIT_TIMEOUT_SEC = float(os.getenv("REDIS_INIT_TIMEOUT_SEC", "3.0"))

# ---- Rate limit config ----
WINDOW_SECONDS = 60
RATE_PREFIX = "rate_limiter:"


_redis: Optional[aioredis.Redis] = None
_redis_init_lock = False


def _get_rate_limit(path: str) -> int:
    if "/api/ai/search" in path:
        return 10
    if "/api/queue/add" in path:
        return 20
    if "/api/webhooks/" in path:
        return 30
    return 60


def _extract_client_ip(request: Request) -> str:
    # Prefer proxy headers (requires that your proxy is trusted and configured)
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()

    x_real_ip = request.headers.get("X-Real-IP")
    if x_real_ip:
        return x_real_ip.strip()

    return request.client.host if request.client else "unknown"


async def _get_redis() -> aioredis.Redis:
    global _redis, _redis_init_lock

    if _redis is not None:
        return _redis

    # simple single-flight (good enough for this middleware)
    if _redis_init_lock:
        # wait a bit for another request to init
        for _ in range(10):
            if _redis is not None:
                return _redis
            await asyncio_sleep(0.05)
        # fallback: continue and try
    _redis_init_lock = True
    try:
        _redis = aioredis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=REDIS_INIT_TIMEOUT_SEC,
            socket_timeout=REDIS_INIT_TIMEOUT_SEC,
        )
        await _redis.ping()
        return _redis
    finally:
        _redis_init_lock = False


async def asyncio_sleep(seconds: float) -> None:
    # local tiny helper to avoid extra imports in hot path
    import asyncio
    await asyncio.sleep(seconds)


def register_rate_limiter(app: FastAPI) -> None:
    @app.middleware("http")
    async def rate_limiting_middleware(request: Request, call_next):
        path = request.url.path
        if path in ["/", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)

        limit = _get_rate_limit(path)
        client_ip = _extract_client_ip(request)

        # eviction key with TTL (evicts itself after WINDOW_SECONDS)
        key = f"{RATE_PREFIX}{client_ip}:{path}"

        try:
            redis = await _get_redis()

            # Atomic rate limiting:
            # - INCR key
            # - if first hit => EXPIRE key for WINDOW_SECONDS
            # Use Lua to avoid race between INCR and EXPIRE
            script = """
            local current = redis.call('INCR', KEYS[1])
            if current == 1 then
              redis.call('EXPIRE', KEYS[1], ARGV[1])
            end
            return current
            """
            current = await redis.eval(script, 1, key, WINDOW_SECONDS)
            current_int = int(current)

            if current_int > limit:
                logger.warning(
                    f"[Rate Limit Blocked] IP {client_ip} превысил лимит на {path} ({limit} запр./мин). current={current_int}"
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Too Many Requests. Вы превысили лимит запросов для этого эндпоинта. Попробуйте позже."
                    },
                    headers={"Retry-After": str(WINDOW_SECONDS)},
                )

        except Exception as e:
            # On Redis failure:
            # - fail-open if REDIS_FAIL_FAST=0
            # - fail-closed otherwise (429 is better than 500? but limiter is unavailable => 503)
            logger.error(f"[RateLimiter] Redis error: {e}")
            if REDIS_FAIL_FAST == 0:
                return await call_next(request)
            return JSONResponse(
                status_code=503,
                content={"detail": "Rate limiter temporarily unavailable."},
            )

        return await call_next(request)
