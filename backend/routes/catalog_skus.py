from __future__ import annotations

import logging
import psycopg2
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import verify_b2b_token
from db import _use_pg, get_db, q
from rate_limiter import register_rate_limiter  # noqa: F401  (keeps import side-effects stable if any)

logger = logging.getLogger("HHB_B2B")

router = APIRouter(tags=["catalog"])


class SkuInput(BaseModel):
    sku: str
    category: Optional[str] = ""
    gost: Optional[str] = ""
    d: Optional[float] = None
    D: Optional[float] = None
    B: Optional[float] = None
    type: Optional[str] = ""
    brand: Optional[str] = ""
    stock: Optional[str] = ""
    price: float = 0
    img: Optional[str] = ""


def get_last_id(cursor) -> int:
    if _use_pg:
        return cursor.fetchone()[0]
    return cursor.lastrowid


@router.get("/api/catalog/skus")
def list_skus(
    category: Optional[str] = None,
    search: Optional[str] = None,
    d_min: Optional[float] = None,
    d_max: Optional[float] = None,
):
    conn = get_db()
    cursor = conn.cursor()
    # Read from the unified products table (+ brands/categories JOIN). The
    # legacy sku_catalog is being retired; this keeps the response shape
    # unchanged so the /admin/proposals frontend keeps working.
    # Column order: id, code, category.name, brand.name, d, d_outer, b_width,
    #               products.name, stock, price_new, img.
    query = """
        SELECT p.id, p.code, c.name, b.name, p.d, p.d_outer, p.b_width, p.name,
               p.stock, p.price_new, p.img
        FROM products p
        LEFT JOIN categories c ON c.id = p.category_id
        LEFT JOIN brands b ON b.id = p.brand_id
        WHERE 1=1
    """.strip()
    params = []

    if category and category != "all":
        query += " AND c.name = %s"
        params.append(category)

    if search:
        query += " AND (p.code ILIKE %s OR p.name ILIKE %s)"
        params.extend([f"%{search}%", f"%{search}%"])

    if d_min is not None:
        query += " AND p.d >= %s"
        params.append(d_min)

    if d_max is not None:
        query += " AND p.d <= %s"
        params.append(d_max)

    query += " ORDER BY p.id ASC"
    cursor.execute(q(query), params)

    rows = cursor.fetchall()
    conn.close()

    # Preserve the legacy response shape (sku, brand, d, D, B, type, price) so
    # the existing frontend /admin/proposals keeps working unchanged.
    return [
        {
            "id": r[0],
            "sku": r[1],          # products.code
            "category": r[2],     # categories.name
            "gost": "",           # not in products; kept for frontend compat
            "d": float(r[4]) if r[4] else None,
            "D": float(r[5]) if r[5] else None,
            "B": float(r[6]) if r[6] else None,
            "type": r[7],         # products.name (description)
            "brand": r[3],        # brands.name
            "stock": str(r[8]) if r[8] is not None else "0",
            "price": float(r[9]) if r[9] else 0,
            "img": r[10],
        }
        for r in rows
    ]


@router.post("/api/catalog/skus", dependencies=[Depends(verify_b2b_token)])
def add_sku(data: SkuInput):
    now = datetime.now().isoformat()

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute(
            q(
                """
                INSERT INTO sku_catalog
                    (sku, category, gost, d_inner, d_outer, b_width, type, brand, stock, price, img, created_at)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """
            ),
            (
                data.sku,
                data.category,
                data.gost,
                data.d,
                data.D,
                data.B,
                data.type,
                data.brand,
                data.stock,
                data.price,
                data.img,
                now,
            ),
        )

        sku_id = get_last_id(cursor)
        conn.commit()
        conn.close()

        logger.info(f"[Catalog] Добавлен SKU #{sku_id}: {data.sku}")
        return {"status": "created", "sku_id": sku_id}

    except psycopg2.IntegrityError:
        conn.close()
        raise HTTPException(status_code=409, detail="SKU с таким артикулом уже существует.")
