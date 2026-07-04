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
        channels = []
        for r in rows:
            ch = _channel_row_to_dict(r)
            ch["members"] = _members_with_names(cur, ch["type"], ch["department_role"], ch["id"])
            channels.append(ch)
        return channels
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
        return {
            "id": channel_id,
            "name": data.name,
            "type": "topic",
            "department_role": None,
            "archived": False,
            "members": _members_with_names(cur, "topic", None, channel_id),
        }
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


def _members_with_names(cur, ctype: str, dept_role: str | None, channel_id: int) -> list[Dict[str, Any]]:
    """Return [{id, username, name}] for a channel — computed by type.

    Reuses an existing cursor (no new connection). general → all staff,
    department → role match, topic → explicit channel_members."""
    if ctype == "topic":
        cur.execute(
            q(
                """SELECT u.id, u.username, u.name FROM channel_members cm
                   JOIN users u ON u.id = cm.user_id
                   WHERE cm.channel_id = %s ORDER BY u.name"""
            ),
            (channel_id,),
        )
    elif ctype == "department":
        cur.execute(
            q("SELECT id, username, name FROM users WHERE role = %s ORDER BY name"),
            (dept_role,),
        )
    else:  # general
        cur.execute(
            q("SELECT id, username, name FROM users WHERE role IN ('admin','manager','employee') ORDER BY name")
        )
    return [{"id": r[0], "username": r[1], "name": r[2]} for r in cur.fetchall()]


# ---------- Membership helper ----------

async def _members_of(channel_id: int) -> list[int]:
    """Return user_ids that can see `channel_id` (sync query). Used by fanout."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(q("SELECT type, department_role FROM channels WHERE id = %s"), (channel_id,))
        row = cur.fetchone()
        if not row:
            return []
        ctype, dept_role = row
        if ctype == "topic":
            cur.execute(q("SELECT user_id FROM channel_members WHERE channel_id = %s"), (channel_id,))
        elif ctype == "department":
            cur.execute(q("SELECT id FROM users WHERE role = %s"), (dept_role,))
        else:  # general
            cur.execute(q("SELECT id FROM users WHERE role IN ('admin','manager','employee')"))
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def _require_channel_access(cur, channel_id: int, current_user: Dict[str, Any]) -> Dict[str, Any]:
    """Raise 403 if the user can't read/write the channel."""
    cur.execute(q("SELECT type, department_role FROM channels WHERE id = %s"), (channel_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Канал не найден")
    ctype, dept_role = row
    role = current_user["role"]
    uid = current_user["id"]
    if ctype == "general":
        return {"type": ctype}
    if ctype == "department":
        if role != dept_role:
            raise HTTPException(403, "Нет доступа к каналу отдела")
        return {"type": ctype}
    # topic
    cur.execute(
        q("SELECT 1 FROM channel_members WHERE channel_id = %s AND user_id = %s"),
        (channel_id, uid),
    )
    if not cur.fetchone():
        raise HTTPException(403, "Нет доступа к каналу")
    return {"type": ctype}


# ---------- Messages ----------

async def list_messages(
    channel_id: int,
    current_user: Dict[str, Any],
    before: int | None = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    _require_staff(current_user)
    conn = get_db()
    try:
        cur = conn.cursor()
        _require_channel_access(cur, channel_id, current_user)
        # LEFT JOIN users: author_name resolves to NULL if the author was deleted
        # (messages.author_id is ON DELETE SET NULL). Frontend falls back to a
        # placeholder name in that case.
        if before:
            cur.execute(
                q(
                    """SELECT m.id, m.channel_id, m.author_id, m.content, m.reply_to_id,
                        m.created_at, m.edited_at, m.deleted_at, u.username, u.name
                        FROM messages m
                        LEFT JOIN users u ON u.id = m.author_id
                        WHERE m.channel_id = %s AND m.id < %s
                        ORDER BY m.id DESC LIMIT %s"""
                ),
                (channel_id, before, limit),
            )
        else:
            cur.execute(
                q(
                    """SELECT m.id, m.channel_id, m.author_id, m.content, m.reply_to_id,
                        m.created_at, m.edited_at, m.deleted_at, u.username, u.name
                        FROM messages m
                        LEFT JOIN users u ON u.id = m.author_id
                        WHERE m.channel_id = %s
                        ORDER BY m.id DESC LIMIT %s"""
                ),
                (channel_id, limit),
            )
        return [_message_row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


async def send_message(
    channel_id: int,
    data: Any,  # MessageCreate
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    _require_staff(current_user)
    # rate limit (Redis) — protects fan-out from floods
    from services.chat_redis import allow_message
    if not allow_message(current_user["id"]):
        raise HTTPException(429, "Слишком много сообщений, попробуйте позже")
    conn = get_db()
    try:
        cur = conn.cursor()
        _require_channel_access(cur, channel_id, current_user)
        cur.execute(
            q(
                """INSERT INTO messages (channel_id, author_id, content, reply_to_id)
                   VALUES (%s, %s, %s, %s) RETURNING id, created_at"""
            ),
            (channel_id, current_user["id"], data.content, data.reply_to_id),
        )
        mid, created_at = cur.fetchone()
        conn.commit()
        return {
            "id": mid,
            "channel_id": channel_id,
            "author_id": current_user["id"],
            "author_username": current_user.get("username"),
            "author_name": current_user.get("name"),
            "content": data.content,
            "reply_to_id": data.reply_to_id,
            "created_at": created_at.isoformat() if created_at else None,
            "edited_at": None,
            "deleted_at": None,
        }
    finally:
        conn.close()


async def edit_message(
    message_id: int,
    data: Any,  # MessageUpdate
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    _require_staff(current_user)
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(q("SELECT author_id FROM messages WHERE id = %s"), (message_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Сообщение не найдено")
        if row[0] != current_user["id"]:
            raise HTTPException(403, "Редактировать может только автор")
        cur.execute(
            q("UPDATE messages SET content = %s, edited_at = now() WHERE id = %s"),
            (data.content, message_id),
        )
        conn.commit()
        return {"id": message_id, "content": data.content, "ok": True}
    finally:
        conn.close()


async def delete_message(
    message_id: int,
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    _require_staff(current_user)
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(q("SELECT author_id FROM messages WHERE id = %s"), (message_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Сообщение не найдено")
        if row[0] != current_user["id"] and current_user["role"] != "admin":
            raise HTTPException(403, "Удалять может только автор или admin")
        cur.execute(q("UPDATE messages SET deleted_at = now() WHERE id = %s"), (message_id,))
        conn.commit()
        return {"id": message_id, "ok": True}
    finally:
        conn.close()


def _message_row_to_dict(r) -> Dict[str, Any]:
    return {
        "id": r[0],
        "channel_id": r[1],
        "author_id": r[2],
        "content": r[3],
        "reply_to_id": r[4],
        "created_at": r[5].isoformat() if r[5] else None,
        "edited_at": r[6].isoformat() if r[6] else None,
        "deleted_at": r[7].isoformat() if r[7] else None,
        # r[8] = users.username, r[9] = users.name (NULL if author deleted)
        "author_username": r[8],
        "author_name": r[9],
    }


# ---------- Read state + unread ----------

async def mark_read(
    channel_id: int,
    last_read_message_id: int,
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    _require_staff(current_user)
    conn = get_db()
    try:
        cur = conn.cursor()
        _require_channel_access(cur, channel_id, current_user)
        cur.execute(
            q(
                """INSERT INTO read_state (user_id, channel_id, last_read_message_id)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (user_id, channel_id) DO UPDATE
                   SET last_read_message_id = GREATEST(read_state.last_read_message_id, EXCLUDED.last_read_message_id)"""
            ),
            (current_user["id"], channel_id, last_read_message_id),
        )
        conn.commit()
        return {"channel_id": channel_id, "last_read_message_id": last_read_message_id, "ok": True}
    finally:
        conn.close()


async def unread_counts(current_user: Dict[str, Any]) -> Dict[int, int]:
    """Return {channel_id: unread_count} for all channels visible to the user."""
    _require_staff(current_user)
    conn = get_db()
    try:
        cur = conn.cursor()
        uid = current_user["id"]
        role = current_user["role"]
        cur.execute(
            q(
                """
                SELECT c.id, c.type, COALESCE(rs.last_read_message_id, 0)
                FROM channels c
                LEFT JOIN read_state rs ON rs.channel_id = c.id AND rs.user_id = %s
                WHERE c.type = 'general'
                   OR (c.type = 'department' AND c.department_role = %s)
                   OR (c.type = 'topic' AND c.id IN (
                       SELECT channel_id FROM channel_members WHERE user_id = %s))
                """
            ),
            (uid, role, uid),
        )
        chans = cur.fetchall()
        result: Dict[int, int] = {}
        for channel_id, _ctype, last_read in chans:
            cur.execute(
                q(
                    """SELECT COUNT(*) FROM messages
                       WHERE channel_id = %s AND id > %s AND deleted_at IS NULL"""
                ),
                (channel_id, last_read),
            )
            result[channel_id] = cur.fetchone()[0]
        return result
    finally:
        conn.close()


# ---------- Membership (topic only) ----------

def _require_topic(cur, channel_id: int) -> None:
    """Raise 400 if channel is not a topic — general/department membership is computed."""
    cur.execute(q("SELECT type FROM channels WHERE id = %s"), (channel_id,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Канал не найден")
    if row[0] != "topic":
        raise HTTPException(400, "Членство редактируется только в тематических каналах")


async def add_member(
    channel_id: int,
    user_id: int,
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    _require_staff(current_user)
    if current_user["role"] not in ("admin", "manager"):
        raise HTTPException(403, "Только admin/manager могут добавлять участников")
    conn = get_db()
    try:
        cur = conn.cursor()
        _require_topic(cur, channel_id)
        cur.execute(
            q("INSERT INTO channel_members (channel_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING"),
            (channel_id, user_id),
        )
        conn.commit()
        return {"channel_id": channel_id, "user_id": user_id, "ok": True}
    finally:
        conn.close()


async def remove_member(
    channel_id: int,
    user_id: int,
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    _require_staff(current_user)
    conn = get_db()
    try:
        cur = conn.cursor()
        _require_topic(cur, channel_id)
        # self can leave; admin/manager can remove others
        if user_id != current_user["id"] and current_user["role"] not in ("admin", "manager"):
            raise HTTPException(403, "Можно удалять только себя")
        cur.execute(
            q("DELETE FROM channel_members WHERE channel_id = %s AND user_id = %s"),
            (channel_id, user_id),
        )
        conn.commit()
        return {"channel_id": channel_id, "user_id": user_id, "ok": True}
    finally:
        conn.close()


# ---------- Channel members listing (for room-info panel) ----------

async def list_members(
    channel_id: int,
    current_user: Dict[str, Any],
) -> list[Dict[str, Any]]:
    """Return [{id, username, name}] for a channel, visible to the caller.
    Computed by type: general=all staff, department=role match, topic=members."""
    _require_staff(current_user)
    conn = get_db()
    try:
        cur = conn.cursor()
        _require_channel_access(cur, channel_id, current_user)
        # re-fetch type/dept_role (already validated by _require_channel_access)
        cur.execute(q("SELECT type, department_role FROM channels WHERE id = %s"), (channel_id,))
        ctype, dept_role = cur.fetchone()
        return _members_with_names(cur, ctype, dept_role, channel_id)
    finally:
        conn.close()


async def list_staff_users(current_user: Dict[str, Any]) -> list[Dict[str, Any]]:
    """All staff users — for the 'invite to channel' dropdown in the create-room modal."""
    _require_staff(current_user)
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            q(
                """SELECT id, username, name FROM users
                   WHERE role IN ('admin','manager','employee') ORDER BY name"""
            )
        )
        return [{"id": r[0], "username": r[1], "name": r[2]} for r in cur.fetchall()]
    finally:
        conn.close()
