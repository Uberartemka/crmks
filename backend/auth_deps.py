from __future__ import annotations

from fastapi import Request


def _get_first_user():
    """Get first user from DB for presentation mode."""
    from db import get_db, q
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("SELECT id, username, name, role FROM users ORDER BY id LIMIT 1"))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "username": row[1], "name": row[2], "role": row[3]}
    return {"id": 0, "username": "guest", "name": "Guest", "role": "admin"}


def get_current_user(request: Request) -> dict:
    """
    DISABLED_FOR_PRESENTATION — any request gets first user from DB.
    No token validation.
    """
    return _get_first_user()


async def get_current_user_async(request: Request) -> dict:
    """
    DISABLED_FOR_PRESENTATION — any request gets first user from DB.
    No token validation.
    """
    return _get_first_user()
