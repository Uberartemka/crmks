"""Catalog v1 API router — public read endpoints + B2B-token stock update.

Reads from the unified catalog (brands/categories/products), NOT from the
legacy sku_catalog. Sites migrate to these endpoints incrementally.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth import verify_b2b_token
from db import get_db
from services.catalog_v1_service import (
    list_products, get_product, list_brands, list_categories, update_stock,
)

logger = logging.getLogger("HHB_B2B")

router = APIRouter(prefix="/api/v1", tags=["catalog-v1"])


@router.get("/products")
def products_list(
    brand: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    d_min: Optional[float] = Query(None),
    d_max: Optional[float] = Query(None),
    d_outer_min: Optional[float] = Query(None),
    d_outer_max: Optional[float] = Query(None),
    seal_type: Optional[str] = Query(None),
    has_stock: Optional[bool] = Query(None),
    is_active: Optional[bool] = Query(True),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    conn = get_db()
    try:
        return list_products(
            conn,
            brand=brand, category=category, search=search,
            d_min=d_min, d_max=d_max,
            d_outer_min=d_outer_min, d_outer_max=d_outer_max,
            seal_type=seal_type, has_stock=has_stock, is_active=is_active,
            limit=limit, offset=offset,
        )
    finally:
        conn.close()


@router.get("/products/{product_id}")
def product_card(product_id: int):
    conn = get_db()
    try:
        p = get_product(conn, product_id)
    finally:
        conn.close()
    if p is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return p


@router.get("/brands")
def brands_list():
    conn = get_db()
    try:
        return list_brands(conn)
    finally:
        conn.close()


@router.get("/categories")
def categories_list():
    conn = get_db()
    try:
        return list_categories(conn)
    finally:
        conn.close()


class StockUpdate(BaseModel):
    stock: Optional[int] = None
    price_old: Optional[float] = None
    price_new: Optional[float] = None


@router.post("/products/{product_id}/stock")
def product_stock_update(
    product_id: int,
    payload: StockUpdate,
    _auth=Depends(verify_b2b_token),
):
    conn = get_db()
    try:
        ok = update_stock(
            conn, product_id,
            stock=payload.stock, price_old=payload.price_old, price_new=payload.price_new,
        )
    finally:
        conn.close()
    if not ok:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"status": "ok", "product_id": product_id}
