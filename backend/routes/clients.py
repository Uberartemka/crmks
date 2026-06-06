from __future__ import annotations

import logging
import traceback
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import _use_pg, get_db, q

logger = logging.getLogger("HHB_B2B")

router = APIRouter(tags=["clients"])


class ClientCreate(BaseModel):
    name: str
    email: Optional[str] = None
    city: Optional[str] = None
    bitrix_id: Optional[str] = None
    discount: int = 0


def get_last_id(cursor) -> int:
    if _use_pg:
        return cursor.fetchone()[0]
    return cursor.lastrowid


@router.get("/api/clients")
def list_clients():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, bitrix_id, email, city, discount, status FROM clients ORDER BY id DESC"
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "name": r[1],
            "bitrix_id": r[2],
            "email": r[3],
            "city": r[4],
            "discount": r[5],
            "status": r[6],
        }
        for r in rows
    ]


@router.post("/api/clients")
def create_client(data: ClientCreate):
    try:
        now = datetime.now().isoformat()
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            q(
                """
                INSERT INTO clients (name, bitrix_id, email, city, discount, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
                """
            ),
            (
                data.name,
                data.bitrix_id,
                data.email,
                data.city,
                data.discount,
                "active",
                now,
            ),
        )
        client_id = get_last_id(cursor)
        conn.commit()
        conn.close()
        return {"status": "created", "client_id": client_id}
    except Exception as e:
        logger.error(f"[!] [create_client ERROR] {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=400, detail=f"Ошибка создания клиента: {e}")


@router.get("/api/clients/{client_id}")
def get_client(client_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        q(
            "SELECT id, name, bitrix_id, email, city, discount, status FROM clients WHERE id = %s"
        ),
        (client_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Клиент не найден.")
    return {
        "id": row[0],
        "name": row[1],
        "bitrix_id": row[2],
        "email": row[3],
        "city": row[4],
        "discount": row[5],
        "status": row[6],
    }


@router.delete("/api/clients/{client_id}")
def delete_client(client_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(q("DELETE FROM clients WHERE id = %s"), (client_id,))
    conn.commit()
    conn.close()
    logger.info(f"[Client] Удалён клиент #{client_id}")
    return {"status": "deleted", "client_id": client_id}
