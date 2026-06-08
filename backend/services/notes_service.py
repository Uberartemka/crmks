from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List

from fastapi import HTTPException

from db import get_db, q, _use_pg


async def list_notes(
    current_user: Dict[str, Any],
) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        q("""
        SELECT id, user_id, title, content, color, pinned, tags, client_id, created_at, updated_at
        FROM notes
        WHERE user_id = %s
        ORDER BY pinned DESC, updated_at DESC
        """),
        (current_user["id"],),
    )
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "user_id": r[1],
            "title": r[2],
            "content": r[3],
            "color": r[4] or "yellow",
            "pinned": bool(r[5]),
            "tags": json.loads(r[6]) if r[6] else [],
            "client_id": r[7],
            "created_at": r[8] or "",
            "updated_at": r[9] or "",
        }
        for r in rows
    ]


async def create_note(
    data: Any,  # expects schemas.tasks.NoteCreate shape
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()

    now = datetime.now().isoformat()
    tags_json = json.dumps(data.tags or [])

    cursor.execute(
        q("""
        INSERT INTO notes (user_id, title, content, color, pinned, tags, client_id, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """),
        (
            current_user["id"],
            data.title,
            data.content,
            data.color,
            int(data.pinned),
            tags_json,
            data.client_id,
            now,
            now,
        ),
    )

    if _use_pg:
        cursor.execute("SELECT LASTVAL()")
    else:
        cursor.execute("SELECT last_insert_rowid()")

    new_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    return {
        "id": new_id,
        "user_id": current_user["id"],
        "title": data.title,
        "content": data.content,
        "color": data.color,
        "pinned": data.pinned,
        "tags": data.tags,
        "client_id": data.client_id,
        "created_at": now,
        "updated_at": now,
    }


async def update_note(
    note_id: int,
    data: Any,  # expects schemas.tasks.NoteCreate shape
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(q("SELECT id, user_id FROM notes WHERE id = %s"), (note_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Заметка не найдена")

    owner_id = row[1]
    # DISABLED_FOR_PRESENTATION — admin role check removed

    now = datetime.now().isoformat()
    tags_json = json.dumps(data.tags or [])

    cursor.execute(
        q("""
        UPDATE notes
        SET title = %s, content = %s, color = %s, pinned = %s, tags = %s, client_id = %s, updated_at = %s
        WHERE id = %s
        """),
        (
            data.title,
            data.content,
            data.color,
            int(data.pinned),
            tags_json,
            data.client_id,
            now,
            note_id,
        ),
    )
    conn.commit()
    conn.close()

    return {
        "id": note_id,
        "user_id": owner_id,
        "title": data.title,
        "content": data.content,
        "color": data.color,
        "pinned": data.pinned,
        "tags": data.tags,
        "client_id": data.client_id,
        "updated_at": now,
    }


async def delete_note(
    note_id: int,
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(q("SELECT user_id FROM notes WHERE id = %s"), (note_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Заметка не найдена")

    owner_id = row[0]
    # DISABLED_FOR_PRESENTATION — admin role check removed

    cursor.execute(q("DELETE FROM notes WHERE id = %s"), (note_id,))
    conn.commit()
    conn.close()
    return {"ok": True}
