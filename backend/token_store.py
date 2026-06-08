"""
Token store with Redis + PostgreSQL fallback.

On Railway there is no Redis, so we fall back to storing tokens in the
`auth_tokens` table in PostgreSQL.  This way login and auth work everywhere.
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

import redis as redis_sync
import redis.asyncio as aioredis

from db import get_db, q, _use_pg

# --- Config ---
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", "86400"))
REDIS_INIT_TIMEOUT_SEC = float(os.getenv("REDIS_INIT_TIMEOUT_SEC", "3.0"))
REDIS_FAIL_FAST = int(os.getenv("REDIS_FAIL_FAST", "0"))  # default 0 — don't crash without Redis

# token -> user_id
_token_prefix = "token:"

_redis_async: Optional[aioredis.Redis] = None
_redis_sync: Optional[redis_sync.Redis] = None
_lock = asyncio.Lock()

_use_fallback = False  # True → use DB table instead of Redis

logger = logging.getLogger("HHB_B2B")


def _key(token: str) -> str:
    return f"{_token_prefix}{token}"


def _ensure_auth_tokens_table() -> None:
    """Create auth_tokens table if it doesn't exist (PG fallback)."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        if _use_pg:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auth_tokens (
                    token_hash VARCHAR(64) PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL
                )
            """)
            # Миграция: обновить expires_at для старых записей (были без timezone)
            cursor.execute("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'auth_tokens' AND column_name = 'expires_at'
                          AND data_type = 'timestamp without time zone'
                    ) THEN
                        ALTER TABLE auth_tokens ALTER COLUMN expires_at TYPE TIMESTAMPTZ
                            USING expires_at AT TIME ZONE 'UTC';
                    END IF;
                END $$;
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_auth_tokens_expires_at
                ON auth_tokens (expires_at)
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auth_tokens (
                    token_hash TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    expires_at TEXT NOT NULL
                )
            """)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"[token_store] Cannot create auth_tokens table: {e}")


async def init_token_store() -> None:
    """
    Initialize token store — try Redis first, fall back to PostgreSQL table.
    """
    global _redis_async, _redis_sync, _use_fallback
    async with _lock:
        if _redis_async is not None and _redis_sync is not None:
            return

        # Try Redis
        try:
            _redis_async = aioredis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=REDIS_INIT_TIMEOUT_SEC,
                socket_timeout=REDIS_INIT_TIMEOUT_SEC,
            )
            await asyncio.wait_for(_redis_async.ping(), timeout=REDIS_INIT_TIMEOUT_SEC)

            _redis_sync = redis_sync.Redis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=REDIS_INIT_TIMEOUT_SEC,
                socket_timeout=REDIS_INIT_TIMEOUT_SEC,
            )
            await asyncio.wait_for(asyncio.to_thread(_redis_sync.ping), timeout=REDIS_INIT_TIMEOUT_SEC)

            _use_fallback = False
            logger.info("[token_store] Redis connected — using Redis token store.")
            return

        except Exception as e:
            logger.warning(f"[token_store] Redis unavailable: {e}")

            # cleanup
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

        # Fallback: use DB table (always runs if Redis unavailable)
        _use_fallback = True
        _ensure_auth_tokens_table()
        logger.info("[token_store] Using PostgreSQL fallback for token storage.")


async def close_token_store() -> None:
    global _redis_async, _redis_sync
    if _redis_async is not None:
        await _redis_async.aclose()
        _redis_async = None
    if _redis_sync is not None:
        await asyncio.to_thread(_redis_sync.close)
        _redis_sync = None


# ──────────────────────────────────────────
#  Internal DB helpers (sync, used by login)
# ──────────────────────────────────────────

def _db_set_token(token: str, user_id: int) -> None:
    import hashlib
    th = hashlib.sha256(token.encode()).hexdigest()
    if _use_pg:
        from datetime import timezone, timedelta
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=TOKEN_TTL_SECONDS)
    else:
        expires_at = datetime.now().isoformat()
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            q("""
                INSERT INTO auth_tokens (token_hash, user_id, expires_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (token_hash) DO UPDATE
                SET user_id = EXCLUDED.user_id, expires_at = EXCLUDED.expires_at
            """),
            (th, user_id, expires_at),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        raise RuntimeError(f"Cannot store token in DB: {e}")


def _db_get_token(token: str) -> Optional[int]:
    import hashlib
    th = hashlib.sha256(token.encode()).hexdigest()
    try:
        conn = get_db()
        cursor = conn.cursor()
        if _use_pg:
            cursor.execute(
                "SELECT user_id FROM auth_tokens WHERE token_hash = %s AND expires_at > NOW()",
                (th,),
            )
        else:
            now = datetime.now().isoformat()
            cursor.execute(
                "SELECT user_id FROM auth_tokens WHERE token_hash = %s AND expires_at > %s",
                (th, now),
            )
        row = cursor.fetchone()
        conn.close()
        if row is None:
            logger.warning(f"[token_store] Token not found or expired: hash={th[:16]}...")
        return int(row[0]) if row else None
    except Exception as e:
        logger.error(f"[token_store] _db_get_token error: {e}")
        return None


def _db_delete_token(token: str) -> None:
    import hashlib
    th = hashlib.sha256(token.encode()).hexdigest()
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(q("DELETE FROM auth_tokens WHERE token_hash = %s"), (th,))
        conn.commit()
        conn.close()
    except Exception:
        pass


def _db_refresh_token(token: str) -> None:
    import hashlib
    th = hashlib.sha256(token.encode()).hexdigest()
    if _use_pg:
        from datetime import timezone, timedelta
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=TOKEN_TTL_SECONDS)
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE auth_tokens SET expires_at = %s WHERE token_hash = %s", (expires_at, th))
            conn.commit()
            conn.close()
        except Exception:
            pass


# ──────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────

async def set_token(token: str, user_id: int) -> None:
    if not _use_fallback and _redis_async is not None:
        await _redis_async.setex(_key(token), TOKEN_TTL_SECONDS, str(user_id))
        return
    _db_set_token(token, user_id)


async def get_token(token: str) -> Optional[int]:
    if not _use_fallback and _redis_async is not None:
        raw = await _redis_async.get(_key(token))
        if raw is None:
            return None
        try:
            return int(raw)
        except ValueError:
            return None
    return _db_get_token(token)


async def delete_token(token: str) -> None:
    if not _use_fallback and _redis_async is not None:
        await _redis_async.delete(_key(token))
        return
    _db_delete_token(token)


async def refresh_token(token: str) -> None:
    if not _use_fallback and _redis_async is not None:
        await _redis_async.expire(_key(token), TOKEN_TTL_SECONDS)
        return
    _db_refresh_token(token)


# ──────────────────────────────────────────
#  Sync API (called by sync FastAPI routes)
# ──────────────────────────────────────────

def set_token_sync(token: str, user_id: int) -> None:
    if not _use_fallback and _redis_sync is not None:
        _redis_sync.setex(_key(token), TOKEN_TTL_SECONDS, str(user_id))
        return
    _db_set_token(token, user_id)


def get_token_sync(token: str) -> Optional[int]:
    if not _use_fallback and _redis_sync is not None:
        raw = _redis_sync.get(_key(token))
        if raw is None:
            return None
        try:
            return int(raw)
        except ValueError:
            return None
    return _db_get_token(token)


def delete_token_sync(token: str) -> None:
    if not _use_fallback and _redis_sync is not None:
        _redis_sync.delete(_key(token))
        return
    _db_delete_token(token)


def refresh_token_sync(token: str) -> None:
    if not _use_fallback and _redis_sync is not None:
        _redis_sync.expire(_key(token), TOKEN_TTL_SECONDS)
        return
    _db_refresh_token(token)
