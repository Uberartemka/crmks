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
