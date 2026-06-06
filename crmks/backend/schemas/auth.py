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


class UserOut(BaseModel):
    id: int
    username: str
    name: str
    role: str
