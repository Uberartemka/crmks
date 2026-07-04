"""Chat business logic: channels, messages, read_state, membership.

Pattern matches orders/defects/machinery services: router → service → db,
Depends(get_current_user), owner-checks. All async functions use sync psycopg2
internally (the codebase standard).
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import HTTPException

from db import get_db, q

_STAFF_ROLES = ("admin", "manager", "employee")


def _require_staff(current_user: Dict[str, Any]) -> None:
    if current_user.get("role") not in _STAFF_ROLES:
        raise HTTPException(403, "Чат доступен только сотрудникам")


# ---------- Channels ----------

async def list_channels(current_user: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Channels visible to the user: general (all staff) + their department +
    topic channels they're a member of."""
    _require_staff(current_user)
    conn = get_db()
    try:
        cur = conn.cursor()
        uid = current_user["id"]
        role = current_user["role"]
        cur.execute(
            q(
                """
                SELECT id, name, type, department_role, archived
                FROM channels
                WHERE type = 'general'
                   OR (type = 'department' AND department_role = %s)
                   OR (type = 'topic' AND id IN (
                       SELECT channel_id FROM channel_members WHERE user_id = %s))
                ORDER BY type, name
                """
            ),
            (role, uid),
        )
        rows = cur.fetchall()
        return [_channel_row_to_dict(r) for r in rows]
    finally:
        conn.close()


async def create_topic_channel(
    data: Any,  # ChannelCreate
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    _require_staff(current_user)
    if current_user["role"] not in ("admin", "manager"):
        raise HTTPException(403, "Только admin/manager могут создавать каналы")
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            q(
                """
                INSERT INTO channels (name, type, created_by)
                VALUES (%s, 'topic', %s) RETURNING id
                """
            ),
            (data.name, current_user["id"]),
        )
        channel_id = cur.fetchone()[0]
        # creator is always a member
        members = {current_user["id"], *data.member_ids}
        for uid in members:
            cur.execute(
                q("INSERT INTO channel_members (channel_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING"),
                (channel_id, uid),
            )
        conn.commit()
        return {"id": channel_id, "name": data.name, "type": "topic", "archived": False}
    finally:
        conn.close()


def _channel_row_to_dict(r) -> Dict[str, Any]:
    return {
        "id": r[0],
        "name": r[1],
        "type": r[2],
        "department_role": r[3],
        "archived": r[4],
    }
