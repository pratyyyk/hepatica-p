from __future__ import annotations

from pydantic import BaseModel, EmailStr


class DevLoginRequest(BaseModel):
    email: EmailStr
    full_name: str | None = None


class DevLoginResponse(BaseModel):
    user_id: str
    email: str
    role: str
