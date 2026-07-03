"""Catalog v1 service — DB access layer for the unified catalog.

All functions take a raw psycopg2 connection (sync) and return plain dicts.
No caching here initially — caching is added in a later task.
"""
import logging
from typing import Any, Optional

logger = logging.getLogger("HHB_B2B")

# Columns returned by the list endpoint (NOT all specs — those are in get_product).
_LIST_COLUMNS = (
    "p.id", "p.code", "p.name",
    "b.id AS brand_id", "b.name AS brand_name", "b.slug AS brand_slug",
    "c.id AS category_id", "c.name AS category_name", "c.slug AS category_slug",
    "p.d", "p.d_outer", "p.b_width",
    "p.price_new", "p.stock", "p.is_active",
)


def list_products(
    conn,
    *,
    brand: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    d_min: Optional[float] = None,
    d_max: Optional[float] = None,
    d_outer_min: Optional[float] = None,
    d_outer_max: Optional[float] = None,
    seal_type: Optional[str] = None,
    has_stock: Optional[bool] = None,
    is_active: Optional[bool] = True,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Filter and paginate products. Returns {items, total, limit, offset}."""
    # Clamp pagination.
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

    where = []
    params: list[Any] = []

    if brand:
        where.append("b.slug = %s")
        params.append(brand)
    if category:
        where.append("c.slug = %s")
        params.append(category)
    if search:
        where.append("(p.code ILIKE %s OR p.name ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    if d_min is not None:
        where.append("p.d >= %s")
        params.append(d_min)
    if d_max is not None:
        where.append("p.d <= %s")
        params.append(d_max)
    if d_outer_min is not None:
        where.append("p.d_outer >= %s")
        params.append(d_outer_min)
    if d_outer_max is not None:
        where.append("p.d_outer <= %s")
        params.append(d_outer_max)
    if seal_type:
        where.append("p.seal_type = %s")
        params.append(seal_type)
    if has_stock is True:
        where.append("p.stock > 0")
    elif has_stock is False:
        where.append("p.stock = 0")
    if is_active is not None:
        where.append("p.is_active = %s")
        params.append(is_active)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    cur = conn.cursor()
    try:
        # Count total (without pagination) for the response metadata.
        cur.execute(
            f"""
            SELECT COUNT(*) FROM products p
            LEFT JOIN brands b ON b.id = p.brand_id
            LEFT JOIN categories c ON c.id = p.category_id
            {where_sql}
            """,
            params,
        )
        total = cur.fetchone()[0]

        cols = ", ".join(_LIST_COLUMNS)
        cur.execute(
            f"""
            SELECT {cols} FROM products p
            LEFT JOIN brands b ON b.id = p.brand_id
            LEFT JOIN categories c ON c.id = p.category_id
            {where_sql}
            ORDER BY p.id ASC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        rows = cur.fetchall()
    finally:
        cur.close()

    items = [_row_to_list_item(r) for r in rows]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def _row_to_list_item(r) -> dict:
    return {
        "id": r[0],
        "code": r[1],
        "name": r[2],
        "brand": ({"id": r[3], "name": r[4], "slug": r[5]} if r[3] else None),
        "category": ({"id": r[6], "name": r[7], "slug": r[8]} if r[6] else None),
        "d": _to_float(r[9]),
        "d_outer": _to_float(r[10]),
        "b_width": _to_float(r[11]),
        "price_new": _to_float(r[12]),
        "stock": r[13],
        "is_active": r[14],
    }


def _to_float(v):
    """numeric -> float for JSON serialization."""
    return float(v) if v is not None else None


# Full column set for the product card (includes all specs).
_PRODUCT_COLUMNS = (
    "p.id", "p.code", "p.name", "p.weight",
    "p.d", "p.d_outer", "p.b_width", "p.rs_min",
    "p.static_load", "p.dynamic_load",
    "p.rpm_oil", "p.rpm_grease", "p.seal_type",
    "p.price_old", "p.price_new", "p.stock", "p.is_active",
    "p.application", "p.img",
    "p.created_at", "p.updated_at",
    "b.id", "b.name", "b.slug",
    "c.id", "c.name", "c.slug",
)


def get_product(conn, product_id: int) -> Optional[dict]:
    """Return the full product card, or None if not found."""
    cur = conn.cursor()
    try:
        cols = ", ".join(_PRODUCT_COLUMNS)
        cur.execute(
            f"""
            SELECT {cols} FROM products p
            LEFT JOIN brands b ON b.id = p.brand_id
            LEFT JOIN categories c ON c.id = p.category_id
            WHERE p.id = %s
            """,
            (product_id,),
        )
        r = cur.fetchone()
    finally:
        cur.close()
    if r is None:
        return None
    return {
        "id": r[0], "code": r[1], "name": r[2], "weight": _to_float(r[3]),
        "d": _to_float(r[4]), "d_outer": _to_float(r[5]), "b_width": _to_float(r[6]),
        "rs_min": _to_float(r[7]), "static_load": _to_float(r[8]),
        "dynamic_load": _to_float(r[9]),
        "rpm_oil": r[10], "rpm_grease": r[11], "seal_type": r[12],
        "price_old": _to_float(r[13]), "price_new": _to_float(r[14]),
        "stock": r[15], "is_active": r[16],
        "application": list(r[17]) if r[17] else [],
        "img": r[18],
        "created_at": r[19].isoformat() if r[19] else None,
        "updated_at": r[20].isoformat() if r[20] else None,
        "brand": ({"id": r[21], "name": r[22], "slug": r[23]} if r[21] else None),
        "category": ({"id": r[24], "name": r[25], "slug": r[26]} if r[24] else None),
    }


def list_brands(conn) -> list:
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, name, slug FROM brands ORDER BY name")
        rows = cur.fetchall()
    finally:
        cur.close()
    return [{"id": r[0], "name": r[1], "slug": r[2]} for r in rows]


def list_categories(conn) -> list:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, name, slug, title, parent_id FROM categories ORDER BY name"
        )
        rows = cur.fetchall()
    finally:
        cur.close()
    return [
        {"id": r[0], "name": r[1], "slug": r[2], "title": r[3], "parent_id": r[4]}
        for r in rows
    ]


def update_stock(
    conn,
    product_id: int,
    *,
    stock: Optional[int] = None,
    price_old: Optional[float] = None,
    price_new: Optional[float] = None,
) -> bool:
    """Update stock/price for a product. Returns True if a row was updated."""
    sets = []
    params: list[Any] = []
    if stock is not None:
        sets.append("stock = %s")
        params.append(int(stock))
    if price_old is not None:
        sets.append("price_old = %s")
        params.append(price_old)
    if price_new is not None:
        sets.append("price_new = %s")
        params.append(price_new)
    if not sets:
        return False
    sets.append("updated_at = now()")
    params.append(product_id)

    cur = conn.cursor()
    try:
        cur.execute(
            f"UPDATE products SET {', '.join(sets)} WHERE id = %s",
            params,
        )
        affected = cur.rowcount
        conn.commit()
    finally:
        cur.close()
    return affected > 0
