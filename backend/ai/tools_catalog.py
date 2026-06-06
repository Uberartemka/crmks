from __future__ import annotations

from typing import Optional

from db import db_cursor, q
from ai_registry import tool


@tool(
    name="list_clients",
    description="Получить список клиентов или найти по названию/городу",
    parameters={
        "type": "object",
        "properties": {
            "search": {
                "type": "string",
                "description": "Поиск по названию, email или городу",
            }
        },
    },
    roles=["admin", "manager", "employee"],
)
def list_clients(ctx: dict, search: Optional[str] = None):
    with db_cursor() as cur:
        if search:
            like = f"%{search}%"
            cur.execute(
                q(
                    """
                    SELECT id, name, email, city, status, discount FROM clients
                    WHERE name ILIKE %s OR email ILIKE %s OR city ILIKE %s
                    ORDER BY name LIMIT 20
                    """
                ),
                (like, like, like),
            )
        else:
            cur.execute(
                q(
                    "SELECT id, name, email, city, status, discount FROM clients ORDER BY name LIMIT 20"
                )
            )
        rows = cur.fetchall()

    return [
        {"id": r[0], "name": r[1], "email": r[2], "city": r[3], "status": r[4], "discount": r[5]}
        for r in rows
    ]


@tool(
    name="prepare_document",
    description="Подготовить документ (ТЭО, КП, аудит)",
    parameters={
        "type": "object",
        "properties": {
            "doc_type": {"type": "string", "enum": ["teo", "kp", "audit"]},
            "client_id": {"type": "integer"},
        },
        "required": ["doc_type"],
    },
    roles=["admin", "manager", "employee"],
)
def prepare_document(ctx: dict, doc_type: str, client_id: Optional[int] = None):
    return {"status": "queued", "doc_type": doc_type, "client_id": client_id, "preview_url": None}
