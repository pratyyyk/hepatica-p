from __future__ import annotations

from pydantic import BaseModel, EmailStr


class DevLoginRequest(BaseModel):
    email: EmailStr
    full_name: str | None = None


class FirebaseLoginRequest(BaseModel):
    email: EmailStr
    password: str


class DevLoginResponse(BaseModel):
    user_id: str
    email: str
    role: str


class AuthSessionResponse(BaseModel):
    authenticated: bool
    user_id: str
    email: str
    role: str
    csrf_token: str | None
    csrf_header_name: str


class LogoutResponse(BaseModel):
    ok: bool
    message: str
