from __future__ import annotations

import os
from typing import Optional, Sequence, Any, TypeVar, List

import asyncpg

from db import _use_pg

_pool: Optional[asyncpg.Pool] = None

_T = TypeVar("_T")


def _get_dsn() -> str:
    # db.py uses DATABASE_URL
    return os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/hhb_b2b",
    )


def _to_asyncpg_sql(sql: str) -> str:
    """
    Convert psycopg2-style placeholders (%s) to asyncpg placeholders ($1..$n).

    Assumption: queries use plain "%s" placeholders and don't contain "%s" inside string literals.
    """
    parts = sql.split("%s")
    if len(parts) == 1:
        return sql

    # number of placeholders must match number of params at call site
    out = parts[0]
    for i in range(1, len(parts)):
        out += f"${i}"
        out += parts[i]
    return out


async def init_async_pool() -> None:
    global _pool
    if _pool is not None:
        return

    if not _use_pg:
        # SQLite mode: keep legacy sync DB access, async pool not available.
        _pool = None
        return

    min_size = int(os.getenv("DB_POOL_MIN", "2"))
    max_size = int(os.getenv("DB_POOL_MAX", "10"))
    command_timeout = float(os.getenv("DB_COMMAND_TIMEOUT_SEC", "30"))

    _pool = await asyncpg.create_pool(
        dsn=_get_dsn(),
        min_size=min_size,
        max_size=max_size,
        command_timeout=command_timeout,
    )


async def get_async_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Async DB pool not initialized. Call init_async_pool() on startup.")
    return _pool


async def close_async_pool() -> None:
    global _pool
    if _pool is None:
        return
    await _pool.close()
    _pool = None


# -------------------------
# High-level query helpers
# -------------------------
async def fetch_one(sql: str, params: Sequence[Any] = ()) -> Optional[asyncpg.Record]:
    pool = await get_async_pool()
    async with pool.acquire() as conn:
        sql2 = _to_asyncpg_sql(sql)
        return await conn.fetchrow(sql2, *params)


async def fetch_all(sql: str, params: Sequence[Any] = ()) -> List[asyncpg.Record]:
    pool = await get_async_pool()
    async with pool.acquire() as conn:
        sql2 = _to_asyncpg_sql(sql)
        return await conn.fetch(sql2, *params)


async def execute(sql: str, params: Sequence[Any] = ()) -> str:
    pool = await get_async_pool()
    async with pool.acquire() as conn:
        sql2 = _to_asyncpg_sql(sql)
        return await conn.execute(sql2, *params)


async def fetch_val(sql: str, params: Sequence[Any] = ()) -> Any:
    pool = await get_async_pool()
    async with pool.acquire() as conn:
        sql2 = _to_asyncpg_sql(sql)
        return await conn.fetchval(sql2, *params)
