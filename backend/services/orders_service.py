from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from db import get_db, q, _use_pg


_SELECT_COLS = (
    "id, client_id, created_by, order_number, name, qty, total, status, "
    "order_date, created_at, updated_at"
)


async def list_orders(
    current_user: Dict[str, Any],
    client_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """List orders.

    Client sees only own orders. Admin/manager may filter by client_id param;
    otherwise all orders are returned.
    """
    conn = get_db()
    cursor = conn.cursor()

    role = current_user.get("role")
    own = current_user.get("client_id")

    if role == "client" and own:
        cursor.execute(
            q(f"SELECT {_SELECT_COLS} FROM orders WHERE client_id = %s ORDER BY created_at DESC"),
            (own,),
        )
    elif client_id:
        cursor.execute(
            q(f"SELECT {_SELECT_COLS} FROM orders WHERE client_id = %s ORDER BY created_at DESC"),
            (client_id,),
        )
    else:
        cursor.execute(q(f"SELECT {_SELECT_COLS} FROM orders ORDER BY created_at DESC"))

    rows = cursor.fetchall()
    conn.close()

    return [_row_to_dict(r) for r in rows]


async def create_order(
    data: Any,  # expects schemas.orders.OrderCreate shape
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    """Create an order.

    Client: client_id = own (must be bound). Admin/manager: client_id from data
    or own.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()

        role = current_user.get("role")
        own = current_user.get("client_id")

        if role == "client":
            if not own:
                raise HTTPException(403, "Ваш аккаунт не привязан к клиенту.")
            target_client_id = own
        else:
            # admin/manager: require explicit client_id (FK-safe — must exist)
            target_client_id = data.client_id or own
            if not target_client_id:
                raise HTTPException(
                    400, "Укажите client_id (для какой компании создаётся заказ)."
                )

        now = datetime.now().isoformat()
        cursor.execute(
            q(
                """
                INSERT INTO orders
                    (client_id, created_by, order_number, name, qty, total, status, order_date, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
            ),
            (
                target_client_id,
                current_user["id"],
                data.order_number,
                data.name,
                data.qty,
                data.total,
                data.status,
                data.order_date,
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
        return {
            "id": new_id,
            "client_id": target_client_id,
            "created_by": current_user["id"],
            "order_number": data.order_number,
            "name": data.name,
            "qty": data.qty,
            "total": data.total,
            "status": data.status,
            "order_date": data.order_date,
            "created_at": now,
            "updated_at": now,
        }
    finally:
        conn.close()


async def update_order(
    order_id: int,
    data: Any,  # expects schemas.orders.OrderUpdate shape
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(q("SELECT id, client_id FROM orders WHERE id = %s"), (order_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Заказ не найден")

        # Close the (read) transaction before potentially raising, so the
        # ACCESS SHARE lock is released even on a 403.
        _check_access(current_user, row[1])

        now = datetime.now().isoformat()
        fields: List[str] = []
        values: List[Any] = []
        for fname in ("order_number", "name", "qty", "total", "status", "order_date"):
            val = getattr(data, fname)
            if val is not None:
                fields.append(f"{fname} = %s")
                values.append(val)

        if not fields:
            raise HTTPException(400, "Нет полей для обновления")

        fields.append("updated_at = %s")
        values.append(now)
        values.append(order_id)

        cursor.execute(
            q(f"UPDATE orders SET {', '.join(fields)} WHERE id = %s"),
            values,
        )
        conn.commit()
        return {"id": order_id, "updated_at": now, "ok": True}
    finally:
        conn.close()


async def delete_order(
    order_id: int,
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(q("SELECT client_id FROM orders WHERE id = %s"), (order_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "Заказ не найден")

        _check_access(current_user, row[0])

        cursor.execute(q("DELETE FROM orders WHERE id = %s"), (order_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


def _check_access(current_user: Dict[str, Any], order_client_id: Any) -> None:
    """Clients may only touch their own orders; admin/manager are unrestricted."""
    role = current_user.get("role")
    own = current_user.get("client_id")
    if role == "client" and own != order_client_id:
        raise HTTPException(403, "Forbidden")


def _row_to_dict(r) -> Dict[str, Any]:
    return {
        "id": r[0],
        "client_id": r[1],
        "created_by": r[2],
        "order_number": r[3],
        "name": r[4],
        "qty": r[5],
        "total": r[6],
        "status": r[7],
        "order_date": r[8],
        "created_at": r[9] or "",
        "updated_at": r[10] or "",
    }
