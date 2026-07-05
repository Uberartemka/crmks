from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class UserLogin(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    password: str
    name: str
    role: str = "employee"
    # Optional binding to a client company (required for role="client").
    client_id: Optional[int] = None


class UserOut(BaseModel):
    id: int
    username: str
    name: str
    role: str
    client_id: Optional[int] = None
    client_name: Optional[str] = None
    avatar_file_id: Optional[int] = None
    avatar_url: Optional[str] = None
