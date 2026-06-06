from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ProposalInput(BaseModel):
    client_id: int
    title: Optional[str] = ""
    discount_global: int = 0


class ProposalItemInput(BaseModel):
    sku_id: int
    qty: int = 1
    discount_item: int = 0


class SendEmailInput(BaseModel):
    recipient_email: Optional[str] = None
    subject: Optional[str] = "Коммерческое предложение HHB / FKD"


class DiscountInput(BaseModel):
    discount_global: int = 0
