from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request

from schemas.orders import OrderCreate, OrderUpdate
from auth_deps import get_current_user as _get_current_user
from services.orders_service import (
    create_order,
    delete_order,
    list_orders,
    update_order,
)

router = APIRouter(tags=["orders"])


def get_current_user():
    async def _dep(request: Request):
        return _get_current_user(request)

    return _dep


@router.get("/api/orders")
async def list_orders_endpoint(
    client_id: Optional[int] = None,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await list_orders(current_user=current_user, client_id=client_id)


@router.post("/api/orders")
async def create_order_endpoint(
    data: OrderCreate,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await create_order(data=data, current_user=current_user)


@router.patch("/api/orders/{order_id}")
async def update_order_endpoint(
    order_id: int,
    data: OrderUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await update_order(order_id=order_id, data=data, current_user=current_user)


@router.delete("/api/orders/{order_id}")
async def delete_order_endpoint(
    order_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user()),
):
    return await delete_order(order_id=order_id, current_user=current_user)
