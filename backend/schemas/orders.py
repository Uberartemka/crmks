from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class OrderCreate(BaseModel):
    order_number: Optional[str] = None
    name: str
    qty: int = 1
    total: float = 0
    status: str = "new"
    order_date: Optional[str] = None
    client_id: Optional[int] = None  # only for admin/manager; client ignores, uses own


class OrderUpdate(BaseModel):
    order_number: Optional[str] = None
    name: Optional[str] = None
    qty: Optional[int] = None
    total: Optional[float] = None
    status: Optional[str] = None
    order_date: Optional[str] = None
