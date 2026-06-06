from __future__ import annotations

import asyncio
from fastapi import HTTPException, Request

from db import _use_pg, get_db, q
from db_async import fetch_one as async_fetch_one
from token_store import get_token_sync, refresh_token_sync


def get_current_user(request: Request) -> dict:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")

    token = auth_header[7:]
    user_id = get_token_sync(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # sliding expiry
    refresh_token_sync(token)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        q("SELECT id, username, name, role FROM users WHERE id = %s"),
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=401, detail="User not found")

    return {"id": row[0], "username": row[1], "name": row[2], "role": row[3]}


async def get_current_user_async(request: Request) -> dict:
    """
    Async-вариант для non-blocking запросов к пользователю.
    Сохраняем sync get_current_user() чтобы не ломать прямые вызовы в AI-роутах.
    """
    if not _use_pg:
        return await asyncio.to_thread(get_current_user, request)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")

    token = auth_header[7:]
    user_id = get_token_sync(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    refresh_token_sync(token)

    row = await async_fetch_one(
        q("SELECT id, username, name, role FROM users WHERE id = %s"),
        (user_id,),
    )
    if not row:
        raise HTTPException(status_code=401, detail="User not found")

    # asyncpg.Record is indexable
    return {"id": row[0], "username": row[1], "name": row[2], "role": row[3]}
