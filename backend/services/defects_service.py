from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from db import get_db, q, _use_pg


_SELECT_COLS = (
    "id, client_id, created_by, equipment, bearing, description, "
    "status, action, detected_at, created_at, updated_at"
)


async def list_defects(
    current_user: Dict[str, Any],
    client_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """List defects.

    Client sees only own defects. Admin/manager may filter by client_id param;
    otherwise all defects are returned.
    """
    conn = get_db()
    cursor = conn.cursor()

    role = current_user.get("role")
    own = current_user.get("client_id")

    if role == "client" and own:
        cursor.execute(
            q(f"SELECT {_SELECT_COLS} FROM defects WHERE client_id = %s ORDER BY created_at DESC"),
            (own,),
        )
    elif client_id:
        cursor.execute(
            q(f"SELECT {_SELECT_COLS} FROM defects WHERE client_id = %s ORDER BY created_at DESC"),
            (client_id,),
        )
    else:
        cursor.execute(q(f"SELECT {_SELECT_COLS} FROM defects ORDER BY created_at DESC"))

    rows = cursor.fetchall()
    conn.close()

    return [_row_to_dict(r) for r in rows]


async def create_defect(
    data: Any,  # expects schemas.defects.DefectCreate shape
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    """Create a defect.

    Client: client_id = own (must be bound). Admin/manager: client_id from data
    or own.
    """
    conn = get_db()
    cursor = conn.cursor()

    role = current_user.get("role")
    own = current_user.get("client_id")

    if role == "client":
        if not own:
            conn.close()
            raise HTTPException(403, "Ваш аккаунт не привязан к клиенту.")
        target_client_id = own
    else:
        # admin/manager: require explicit client_id (or fall back to own binding)
        target_client_id = data.client_id or own
        if not target_client_id:
            conn.close()
            raise HTTPException(400, "Укажите client_id (для какой компании создаётся дефект).")

    now = datetime.now().isoformat()
    cursor.execute(
        q(
            """
            INSERT INTO defects
                (client_id, created_by, equipment, bearing, description, status, action, detected_at, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
        ),
        (
            target_client_id,
            current_user["id"],
            data.equipment,
            data.bearing,
            data.description,
            data.status,
            data.action,
            data.detected_at,
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
        "client_id": target_client_id,
        "created_by": current_user["id"],
        "equipment": data.equipment,
        "bearing": data.bearing,
        "description": data.description,
        "status": data.status,
        "action": data.action,
        "detected_at": data.detected_at,
        "created_at": now,
        "updated_at": now,
    }


async def update_defect(
    defect_id: int,
    data: Any,  # expects schemas.defects.DefectUpdate shape
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(q("SELECT id, client_id FROM defects WHERE id = %s"), (defect_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Дефект не найден")

        # Close the (read) transaction before potentially raising, so the
        # ACCESS SHARE lock is released even on a 403.
        _check_access(current_user, row[1])

        now = datetime.now().isoformat()
        fields: List[str] = []
        values: List[Any] = []
        for fname in ("equipment", "bearing", "description", "status", "action", "detected_at"):
            val = getattr(data, fname)
            if val is not None:
                fields.append(f"{fname} = %s")
                values.append(val)

        if not fields:
            raise HTTPException(400, "Нет полей для обновления")

        fields.append("updated_at = %s")
        values.append(now)
        values.append(defect_id)

        cursor.execute(
            q(f"UPDATE defects SET {', '.join(fields)} WHERE id = %s"),
            values,
        )
        conn.commit()
        return {"id": defect_id, "updated_at": now, "ok": True}
    finally:
        conn.close()


async def delete_defect(
    defect_id: int,
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(q("SELECT client_id FROM defects WHERE id = %s"), (defect_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Дефект не найден")

        _check_access(current_user, row[0])

        cursor.execute(q("DELETE FROM defects WHERE id = %s"), (defect_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


def _check_access(current_user: Dict[str, Any], defect_client_id: Any) -> None:
    """Clients may only touch their own defects; admin/manager are unrestricted."""
    role = current_user.get("role")
    own = current_user.get("client_id")
    if role == "client" and own != defect_client_id:
        raise HTTPException(403, "Forbidden")


def _row_to_dict(r) -> Dict[str, Any]:
    return {
        "id": r[0],
        "client_id": r[1],
        "created_by": r[2],
        "equipment": r[3],
        "bearing": r[4],
        "description": r[5],
        "status": r[6],
        "action": r[7],
        "detected_at": r[8],
        "created_at": r[9] or "",
        "updated_at": r[10] or "",
    }
