from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db import get_db, q
from auth_deps import get_current_user
from schemas.leads import LeadAssign, LeadStatusUpdate, PatchLeadRequest

logger = logging.getLogger("HHB_B2B")

router = APIRouter(tags=["leads"])


class LeadCreate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    city: Optional[str] = None
    contacts: Optional[str] = None
    need_description: Optional[str] = None
    query: Optional[str] = None
    region: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[int] = None


@router.get("/api/leads")
def list_leads(
    query: Optional[str] = None,
    region: Optional[str] = None,
    status: Optional[str] = None,
    assigned_to: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
):
    conn = get_db()
    cursor = conn.cursor()

    sql = q(
        """
        SELECT l.id, l.name, l.category, l.city, l.contacts, l.need_description,
               l.query, l.region, l.status, l.assigned_to, u.name, l.call_count, l.created_at
        FROM parsed_leads l
        LEFT JOIN users u ON u.id = l.assigned_to
        WHERE 1=1
        """
    )
    params: list[object] = []

    # Role filtering: employees see only assigned_to = self or unassigned
    if current_user["role"] == "employee":
        sql += q(" AND (l.assigned_to = %s OR l.assigned_to IS NULL)")
        params.append(current_user["id"])

    if query:
        # db.q handles placeholder differences internally only for _use_pg;
        # keep same logic as legacy main.py.
        from db import _use_pg  # local import to keep module lightweight

        if _use_pg:
            sql += q(" AND l.query ILIKE %s")
            params.append(f"%{query}%")
        else:
            sql += q(" AND l.query LIKE %s")
            params.append(f"%{query}%")

    if region:
        sql += q(" AND l.region = %s")
        params.append(region)

    if status:
        sql += q(" AND l.status = %s")
        params.append(status)

    if assigned_to is not None:
        sql += q(" AND l.assigned_to = %s")
        params.append(assigned_to)

    sql += q(" ORDER BY l.created_at DESC")

    cursor.execute(sql, tuple(params))
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "name": r[1],
            "category": r[2],
            "city": r[3],
            "contacts": r[4],
            "need_description": r[5],
            "query": r[6],
            "region": r[7],
            "status": r[8],
            "assigned_to": r[9],
            "assigned_name": r[10],
            "call_count": r[11] or 0,
            "created_at": r[12],
        }
        for r in rows
    ]


@router.post("/api/leads")
def create_lead(data: LeadCreate, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    assigned_to = data.assigned_to
    # Employees can only create leads assigned to themselves
    if current_user["role"] == "employee":
        if not assigned_to:
            assigned_to = current_user["id"]
        elif assigned_to != current_user["id"]:
            conn.close()
            raise HTTPException(status_code=403, detail="Forbidden")

    cursor.execute(
        q(
            """
            INSERT INTO parsed_leads
                (name, category, city, contacts, need_description, query, region, status, assigned_to, created_at, updated_at)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """
        ),
        (
            data.name,
            data.category,
            data.city,
            data.contacts,
            data.need_description,
            data.query,
            data.region,
            data.status or "новый",
            assigned_to,
            now,
            now,
        ),
    )

    lid = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return {"id": lid, "status": "created"}


@router.put("/api/leads/{lead_id}/assign")
def assign_lead(
    lead_id: int, data: LeadAssign, current_user: dict = Depends(get_current_user)
):
    if current_user["role"] not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Forbidden")

    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    cursor.execute(
        q(
            """
            UPDATE parsed_leads
            SET assigned_to = %s, updated_at = %s
            WHERE id = %s
            """
        ),
        (data.user_id, now, lead_id),
    )
    conn.commit()
    conn.close()
    return {"status": "assigned", "lead_id": lead_id, "assigned_to": data.user_id}


@router.put("/api/leads/{lead_id}/status")
def update_lead_status(
    lead_id: int, data: LeadStatusUpdate, current_user: dict = Depends(get_current_user)
):
    conn = get_db()
    cursor = conn.cursor()

    if current_user["role"] == "employee":
        cursor.execute(
            q("SELECT assigned_to FROM parsed_leads WHERE id = %s"),
            (lead_id,),
        )
        row = cursor.fetchone()
        if not row or row[0] != current_user["id"]:
            conn.close()
            raise HTTPException(status_code=403, detail="Forbidden")

    now = datetime.now().isoformat()
    cursor.execute(
        q(
            """
            UPDATE parsed_leads
            SET status = %s, updated_at = %s
            WHERE id = %s
            """
        ),
        (data.status, now, lead_id),
    )
    conn.commit()
    conn.close()
    return {"status": "updated", "lead_id": lead_id, "new_status": data.status}


def build_update_sql(
    table: str, fields: dict[str, Any], allowed: set[str]
) -> tuple[str, list[Any]]:
    """
    Build UPDATE ... SET ... using only whitelisted column names.

    Important: this function only interpolates column identifiers (safe because they
    are validated against `allowed`). Values always go to DB placeholders (%s),
    so SQL injection via values is not possible.
    """
    if table != "parsed_leads":
        raise ValueError("Unexpected table for build_update_sql")

    filtered: dict[str, Any] = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not filtered:
        raise ValueError("No fields to update")

    set_parts: list[str] = []
    values: list[Any] = []
    for col, val in filtered.items():
        set_parts.append(f"{col} = %s")
        values.append(val)

    sql = f"UPDATE {table} SET {', '.join(set_parts)}"
    return sql, values


@router.patch("/api/leads/{lead_id}")
def patch_lead(
    lead_id: int,
    data: PatchLeadRequest,
    current_user: dict = Depends(get_current_user),
):
    conn = get_db()
    cursor = conn.cursor()

    if current_user["role"] == "employee":
        cursor.execute(
            q("SELECT assigned_to FROM parsed_leads WHERE id = %s"),
            (lead_id,),
        )
        row = cursor.fetchone()
        if not row or row[0] != current_user["id"]:
            conn.close()
            raise HTTPException(status_code=403, detail="Forbidden")

    now = datetime.now().isoformat()
    allowed = {
        "name",
        "category",
        "city",
        "contacts",
        "need_description",
        "query",
        "region",
        "status",
    }

    payload = data.model_dump(exclude_none=True)

    try:
        sql_base, values = build_update_sql("parsed_leads", payload, allowed)
    except ValueError as e:
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))

    sql = f"{sql_base}, updated_at = %s WHERE id = %s"
    cursor.execute(q(sql), (*values, now, lead_id))
    conn.commit()
    conn.close()

    updated_fields = [k for k in payload.keys() if k in allowed]
    return {"status": "updated", "lead_id": lead_id, "fields": updated_fields}


@router.delete("/api/leads/{lead_id}")
def delete_lead(lead_id: int, current_user: dict = Depends(get_current_user)):
    """
    Удалить лид из parsed_leads.
    Разрешено только admin и manager.
    """
    if current_user["role"] not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Forbidden")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(q("DELETE FROM parsed_leads WHERE id = %s"), (lead_id,))
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()

    if deleted_count == 0:
        raise HTTPException(status_code=404, detail="Лид не найден")

    return {"status": "deleted", "lead_id": lead_id}
