import asyncio
import logging
import os
from typing import Optional

import redis as redis_sync
import redis.asyncio as aioredis


# --- Config ---
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", "86400"))
REDIS_INIT_TIMEOUT_SEC = float(os.getenv("REDIS_INIT_TIMEOUT_SEC", "3.0"))
REDIS_FAIL_FAST = int(os.getenv("REDIS_FAIL_FAST", "1"))

# token -> user_id
_token_prefix = "token:"


_redis_async: Optional[aioredis.Redis] = None
_redis_sync: Optional[redis_sync.Redis] = None
_lock = asyncio.Lock()


def _key(token: str) -> str:
    return f"{_token_prefix}{token}"


async def init_token_store() -> None:
    """
    Инициализация Redis token_store.

    По умолчанию (REDIS_FAIL_FAST=1) — пробрасываем ошибку при недоступности Redis.
    Если REDIS_FAIL_FAST=0 — сервер стартует без token_store (для локальных smoke/DEV),
    но endpoints, требующие user-token auth, будут недоступны.
    """
    global _redis_async, _redis_sync
    async with _lock:
        if _redis_async is not None and _redis_sync is not None:
            return

        try:
            # async client
            _redis_async = aioredis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=REDIS_INIT_TIMEOUT_SEC,
                socket_timeout=REDIS_INIT_TIMEOUT_SEC,
            )
            await asyncio.wait_for(_redis_async.ping(), timeout=REDIS_INIT_TIMEOUT_SEC)

            # sync client
            _redis_sync = redis_sync.Redis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=REDIS_INIT_TIMEOUT_SEC,
                socket_timeout=REDIS_INIT_TIMEOUT_SEC,
            )
            await asyncio.wait_for(asyncio.to_thread(_redis_sync.ping), timeout=REDIS_INIT_TIMEOUT_SEC)
        except Exception as e:
            if REDIS_FAIL_FAST == 1:
                raise

            logging.getLogger("HHB_B2B").warning(
                f"[token_store] Redis недоступен, пропускаем init (fail_fast=0): {e}"
            )

            # cleanup partially created clients
            try:
                if _redis_async is not None:
                    await _redis_async.aclose()
            except Exception:
                pass
            try:
                if _redis_sync is not None:
                    await asyncio.to_thread(_redis_sync.close)
            except Exception:
                pass

            _redis_async = None
            _redis_sync = None
            return


async def close_token_store() -> None:
    global _redis_async, _redis_sync
    if _redis_async is not None:
        await _redis_async.aclose()
        _redis_async = None

    if _redis_sync is not None:
        # redis-py sync close
        await asyncio.to_thread(_redis_sync.close)
        _redis_sync = None


# -------------------------
# Async API
# -------------------------
async def set_token(token: str, user_id: int) -> None:
    if _redis_async is None:
        raise RuntimeError("token_store is not initialized")
    await _redis_async.setex(_key(token), TOKEN_TTL_SECONDS, str(user_id))


async def get_token(token: str) -> Optional[int]:
    if _redis_async is None:
        return None
    raw = await _redis_async.get(_key(token))
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


async def delete_token(token: str) -> None:
    if _redis_async is None:
        raise RuntimeError("token_store is not initialized")
    await _redis_async.delete(_key(token))


async def refresh_token(token: str) -> None:
    """
    Sliding expiry: продлеваем TTL при активности.
    """
    if _redis_async is None:
        return
    await _redis_async.expire(_key(token), TOKEN_TTL_SECONDS)


# -------------------------
# Sync API
# -------------------------
def set_token_sync(token: str, user_id: int) -> None:
    if _redis_sync is None:
        raise RuntimeError("token_store is not initialized")
    _redis_sync.setex(_key(token), TOKEN_TTL_SECONDS, str(user_id))


def get_token_sync(token: str) -> Optional[int]:
    if _redis_sync is None:
        return None
    raw = _redis_sync.get(_key(token))
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def delete_token_sync(token: str) -> None:
    if _redis_sync is None:
        raise RuntimeError("token_store is not initialized")
    _redis_sync.delete(_key(token))


def refresh_token_sync(token: str) -> None:
    if _redis_sync is None:
        return
    _redis_sync.expire(_key(token), TOKEN_TTL_SECONDS)
