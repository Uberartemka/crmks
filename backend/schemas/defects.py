from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class DefectCreate(BaseModel):
    equipment: str
    bearing: Optional[str] = None
    description: str = ""
    status: str = "new"
    action: Optional[str] = None
    detected_at: Optional[str] = None
    client_id: Optional[int] = None  # only for admin/manager; client ignores, uses own


class DefectUpdate(BaseModel):
    equipment: Optional[str] = None
    bearing: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    action: Optional[str] = None
    detected_at: Optional[str] = None
