from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CalendarEventIn(BaseModel):
    title: str
    description: Optional[str] = None
    kind: str = "meeting"
    start: datetime
    end: Optional[datetime] = None
    all_day: bool = False
    location: Optional[str] = None
    client_id: Optional[int] = None
    color: str = "blue"
