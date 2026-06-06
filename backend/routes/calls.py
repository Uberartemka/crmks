from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from db import get_db, q
from auth_deps import get_current_user
from schemas.tasks import CallLogCreate

logger = logging.getLogger("HHB_B2B")

router = APIRouter(tags=["calls"])


@router.get("/api/calls")
def list_calls(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()

    if current_user["role"] in ("admin", "manager"):
        cursor.execute(
            q(
                """
                SELECT c.id, c.user_id, u.name, c.client_id, c.lead_id, c.client_name, c.from_number, c.to_number, c.direction,
                       c.call_date, c.status, c.duration, c.recording_url, c.notes, c.is_new_registration, c.bitrix_call_id, c.created_at, c.updated_at
                FROM call_logs c
                JOIN users u ON u.id = c.user_id
                ORDER BY c.call_date DESC, c.created_at DESC
                """
            )
        )
    else:
        cursor.execute(
            q(
                """
                SELECT c.id, c.user_id, u.name, c.client_id, c.lead_id, c.client_name, c.from_number, c.to_number, c.direction,
                       c.call_date, c.status, c.duration, c.recording_url, c.notes, c.is_new_registration, c.bitrix_call_id, c.created_at, c.updated_at
                FROM call_logs c
                JOIN users u ON u.id = c.user_id
                WHERE c.user_id = %s
                ORDER BY c.call_date DESC, c.created_at DESC
                """
            ),
            (current_user["id"],),
        )

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "user_id": r[1],
            "user_name": r[2],
            "client_id": r[3],
            "lead_id": r[4],
            "client_name": r[5],
            "from_number": r[6],
            "to_number": r[7],
            "direction": r[8],
            "call_date": r[9],
            "status": r[10],
            "duration": r[11],
            "recording_url": r[12],
            "notes": r[13],
            "is_new_registration": bool(r[14]),
            "bitrix_call_id": r[15],
            "created_at": r[16],
            "updated_at": r[17],
        }
        for r in rows
    ]


@router.post("/api/calls")
def create_call(data: CallLogCreate, current_user: dict = Depends(get_current_user)):
    try:
        conn = get_db()
        cursor = conn.cursor()
        now = datetime.now().isoformat()

        cursor.execute(
            q(
                """
                INSERT INTO call_logs (user_id, client_id, lead_id, client_name, from_number, to_number, direction,
                                       call_date, status, duration, recording_url, notes, is_new_registration, bitrix_call_id, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                """
            ),
            (
                current_user["id"],
                data.client_id,
                data.lead_id,
                data.client_name,
                data.from_number,
                data.to_number,
                data.direction,
                data.call_date,
                data.status,
                data.duration,
                data.recording_url,
                data.notes,
                int(data.is_new_registration),
                data.bitrix_call_id,
                now,
                now,
            ),
        )

        conn.commit()
        cid_row = cursor.fetchone()
        cid = cid_row[0] if cid_row else None
        conn.close()

        return {
            "id": cid,
            "user_id": current_user["id"],
            "client_name": data.client_name,
            "call_date": data.call_date,
            "status": data.status,
            "notes": data.notes,
            "is_new_registration": data.is_new_registration,
        }
    except Exception as e:
        logger.exception("[create_call ERROR] %s", e)
        raise HTTPException(status_code=400, detail=f"Ошибка сохранения звонка: {e}")


@router.put("/api/calls/{call_id}")
def update_call(call_id: int, data: CallLogCreate, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()

    if current_user["role"] not in ("admin", "manager"):
        cursor.execute(q("SELECT user_id FROM call_logs WHERE id = %s"), (call_id,))
        row = cursor.fetchone()
        if not row or row[0] != current_user["id"]:
            conn.close()
            raise HTTPException(status_code=403, detail="Forbidden")

    now = datetime.now().isoformat()
    cursor.execute(
        q(
            """
            UPDATE call_logs
            SET client_id = %s, lead_id = %s, client_name = %s, from_number = %s, to_number = %s,
                direction = %s, call_date = %s, status = %s, duration = %s, recording_url = %s, notes = %s,
                is_new_registration = %s, bitrix_call_id = %s, updated_at = %s
            WHERE id = %s
            """
        ),
        (
            data.client_id,
            data.lead_id,
            data.client_name,
            data.from_number,
            data.to_number,
            data.direction,
            data.call_date,
            data.status,
            data.duration,
            data.recording_url,
            data.notes,
            int(data.is_new_registration),
            data.bitrix_call_id,
            now,
            call_id,
        ),
    )

    conn.commit()
    conn.close()
    return {"status": "updated", "id": call_id}


@router.delete("/api/calls/{call_id}")
def delete_call(call_id: int, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()

    if current_user["role"] not in ("admin", "manager"):
        cursor.execute(q("SELECT user_id FROM call_logs WHERE id = %s"), (call_id,))
        row = cursor.fetchone()
        if not row or row[0] != current_user["id"]:
            conn.close()
            raise HTTPException(status_code=403, detail="Forbidden")

    cursor.execute(q("DELETE FROM call_logs WHERE id = %s"), (call_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted", "id": call_id}
