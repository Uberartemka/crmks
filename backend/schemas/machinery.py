from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class MachineryCreate(BaseModel):
    name: str
    node: Optional[str] = None
    bearing: Optional[str] = None
    brand: Optional[str] = None
    install_date: Optional[str] = None
    wear: int = 0
    status: str = "normal"
    client_id: Optional[int] = None  # only for admin/manager; client ignores, uses own


class MachineryUpdate(BaseModel):
    name: Optional[str] = None
    node: Optional[str] = None
    bearing: Optional[str] = None
    brand: Optional[str] = None
    install_date: Optional[str] = None
    wear: Optional[int] = None
    status: Optional[str] = None
