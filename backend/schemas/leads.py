from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, model_validator


class LeadOut(BaseModel):
    id: int
    name: str
    category: Optional[str]
    city: Optional[str]
    contacts: Optional[str]
    need_description: Optional[str]
    query: Optional[str]
    region: Optional[str]
    status: str
    assigned_to: Optional[int]
    assigned_name: Optional[str]
    call_count: int
    created_at: Optional[str]


class LeadAssign(BaseModel):
    user_id: Optional[int]


class LeadStatusUpdate(BaseModel):
    status: str


class PatchLeadRequest(BaseModel):
    # Whitelist fields that are allowed for PATCH /api/leads/{lead_id}
    name: Optional[str] = None
    category: Optional[str] = None
    city: Optional[str] = None
    contacts: Optional[str] = None
    need_description: Optional[str] = None
    query: Optional[str] = None
    region: Optional[str] = None
    status: Optional[str] = None

    class Config:
        extra = "forbid"

    @model_validator(mode="after")
    def validate_not_empty(self) -> "PatchLeadRequest":
        fields = (
            self.name,
            self.category,
            self.city,
            self.contacts,
            self.need_description,
            self.query,
            self.region,
            self.status,
        )
        if all(v is None for v in fields):
            raise ValueError("At least one field must be provided")
        return self
