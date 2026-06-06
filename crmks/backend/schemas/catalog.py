from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


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
