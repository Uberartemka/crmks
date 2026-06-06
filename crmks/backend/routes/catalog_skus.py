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
    query = """
        SELECT id, sku, category, gost, d_inner, d_outer, b_width, type, brand, stock, price, img
        FROM sku_catalog
        WHERE 1=1
    """.strip()
    params = []

    if category and category != "all":
        query += " AND category = %s"
        params.append(category)

    if search:
        query += " AND (sku ILIKE %s OR type ILIKE %s OR gost ILIKE %s)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    if d_min is not None:
        query += " AND d_inner >= %s"
        params.append(d_min)

    if d_max is not None:
        query += " AND d_inner <= %s"
        params.append(d_max)

    query += " ORDER BY id ASC"
    cursor.execute(q(query), params)

    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "sku": r[1],
            "category": r[2],
            "gost": r[3],
            "d": float(r[4]) if r[4] else None,
            "D": float(r[5]) if r[5] else None,
            "B": float(r[6]) if r[6] else None,
            "type": r[7],
            "brand": r[8],
            "stock": r[9],
            "price": float(r[10]) if r[10] else 0,
            "img": r[11],
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
