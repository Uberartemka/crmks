from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from db import get_db, q, _use_pg
from auth_deps import get_current_user
from schemas.calendar import CalendarEventIn
from utils.db_utils import get_last_id

router = APIRouter()


@router.get("/api/events")
def list_events(from_date: Optional[str] = None, to_date: Optional[str] = None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        q("""
        SELECT id, title, description, kind, start, "end", all_day, location, client_id, color, created_at, updated_at
        FROM calendar_events
        WHERE (%s IS NULL OR start >= %s) AND (%s IS NULL OR start <= %s)
        ORDER BY start
    """),
        (from_date, from_date, to_date, to_date),
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "title": r[1],
            "description": r[2],
            "kind": r[3],
            "start": r[4],
            "end": r[5],
            "all_day": r[6],
            "location": r[7],
            "client_id": r[8],
            "color": r[9],
            "created_at": r[10],
            "updated_at": r[11],
        }
        for r in rows
    ]


@router.post("/api/events")
def create_event(data: CalendarEventIn, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute(
        q("""
        INSERT INTO calendar_events (user_id, created_by, title, description, kind, start, "end", all_day, location, client_id, color, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
    """),
        (
            current_user["id"],
            current_user["id"],
            data.title,
            data.description,
            data.kind,
            data.start.isoformat(),
            data.end.isoformat() if data.end else None,
            data.all_day,
            data.location,
            data.client_id,
            data.color,
            now,
            now,
        ),
    )
    event_id = get_last_id(cursor)
    conn.commit()
    conn.close()
    return {"id": event_id, **data.dict(), "created_at": now, "updated_at": now}


@router.patch("/api/events/{event_id}")
def update_event(event_id: int, data: CalendarEventIn):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    cursor.execute(
        q("""
        UPDATE calendar_events SET title=%s, description=%s, kind=%s, start=%s, "end"=%s,
        all_day=%s, location=%s, client_id=%s, color=%s, updated_at=%s WHERE id=%s
    """),
        (
            data.title,
            data.description,
            data.kind,
            data.start.isoformat(),
            data.end.isoformat() if data.end else None,
            data.all_day,
            data.location,
            data.client_id,
            data.color,
            now,
            event_id,
        ),
    )
    conn.commit()
    conn.close()
    return {"id": event_id, **data.dict(), "updated_at": now}


@router.delete("/api/events/{event_id}")
def delete_event(event_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("DELETE FROM calendar_events WHERE id = %s"), (event_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}
