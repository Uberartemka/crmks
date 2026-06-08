"""
Token store — stores auth tokens in PostgreSQL (or SQLite fallback).

Tokens are stored as SHA256 hashes in the `auth_tokens` table.
No Redis dependency. Works everywhere (Railway, local dev, etc.).
"""

import logging
import os
from datetime import datetime
from typing import Optional

from db import get_db, q, _use_pg

# --- Config ---
TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", "86400"))

# Token storage: always uses PostgreSQL (no Redis dependency).
# token is stored as SHA256 hash -> user_id in auth_tokens table.

logger = logging.getLogger("HHB_B2B")


def _ensure_auth_tokens_table() -> None:
    """Create auth_tokens table if it doesn't exist."""
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
    Initialize token store — ensure the auth_tokens table exists.
    No Redis dependency. Always uses PostgreSQL (or SQLite fallback).
    """
    _ensure_auth_tokens_table()
    logger.info("[token_store] Token store initialized (PostgreSQL backend).")


async def close_token_store() -> None:
    """Nothing to close — DB connections are managed by db.py."""
    pass


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
    _db_set_token(token, user_id)


async def get_token(token: str) -> Optional[int]:
    return _db_get_token(token)


async def delete_token(token: str) -> None:
    _db_delete_token(token)


async def refresh_token(token: str) -> None:
    _db_refresh_token(token)


# ──────────────────────────────────────────
#  Sync API (called by sync FastAPI routes)
# ──────────────────────────────────────────

def set_token_sync(token: str, user_id: int) -> None:
    _db_set_token(token, user_id)


def get_token_sync(token: str) -> Optional[int]:
    return _db_get_token(token)


def delete_token_sync(token: str) -> None:
    _db_delete_token(token)


def refresh_token_sync(token: str) -> None:
    _db_refresh_token(token)
