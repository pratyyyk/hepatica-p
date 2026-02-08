from __future__ import annotations

import json
import time
from functools import lru_cache
from typing import Any

import requests
from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import AuthSession, User
from app.db.session import get_db
from app.services.audit import record_auth_failure


class AuthContext(BaseModel):
    user_id: str
    email: str
    role: str = "DOCTOR"
    session_id: str | None = None


class CognitoJwksCache:
    def __init__(self) -> None:
        self.data: dict[str, Any] | None = None
        self.expires_at: float = 0

    def get(self, settings: Settings) -> dict[str, Any]:
        if self.data and time.time() < self.expires_at:
            return self.data
        if not settings.cognito_user_pool_id:
            raise HTTPException(status_code=500, detail="Cognito user pool not configured")
        url = (
            f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/"
            f"{settings.cognito_user_pool_id}/.well-known/jwks.json"
        )
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        self.data = resp.json()
        self.expires_at = time.time() + 3600
        return self.data


@lru_cache
def _jwks_cache() -> CognitoJwksCache:
    return CognitoJwksCache()


def _is_dev_header_mode_enabled(settings: Settings) -> bool:
    return (
        settings.environment.lower() == "development"
        and settings.auth_mode == "dev_header"
        and settings.enable_dev_auth
    )


def verify_cognito_token(token: str, settings: Settings) -> AuthContext:
    jwks = _jwks_cache().get(settings)
    unverified = jwt.get_unverified_header(token)
    kid = unverified.get("kid")
    key = next((k for k in jwks["keys"] if k.get("kid") == kid), None)
    if not key:
        raise HTTPException(status_code=401, detail="Unable to verify token key")

    issuer = f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/{settings.cognito_user_pool_id}"
    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.cognito_client_id,
            issuer=issuer,
            options={"verify_at_hash": False},
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    email = payload.get("email") or payload.get("username")
    sub = payload.get("sub")
    if not sub or not email:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    groups_raw = payload.get("cognito:groups", [])
    if isinstance(groups_raw, str):
        try:
            groups = json.loads(groups_raw)
        except json.JSONDecodeError:
            groups = [groups_raw]
    else:
        groups = groups_raw

    role = "DOCTOR" if "DOCTOR" in groups or not groups else str(groups[0])
    return AuthContext(user_id=sub, email=email, role=role)


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthContext:
    if _is_dev_header_mode_enabled(settings):
        dev_email = request.headers.get("x-user-email")
        if not dev_email:
            record_auth_failure(reason="DEV_HEADER_MISSING", metadata={"path": request.url.path})
            raise HTTPException(status_code=401, detail="x-user-email required in local dev auth mode")
        return AuthContext(user_id=dev_email, email=dev_email, role="DOCTOR", session_id=None)

    session_id = request.cookies.get(settings.session_cookie_name)
    if not session_id:
        record_auth_failure(reason="SESSION_COOKIE_MISSING", metadata={"path": request.url.path})
        raise HTTPException(status_code=401, detail="Missing session")

    auth_session = db.get(AuthSession, session_id)
    if not auth_session:
        record_auth_failure(reason="SESSION_INVALID", metadata={"path": request.url.path})
        raise HTTPException(status_code=401, detail="Invalid session")

    if auth_session.revoked_at is not None:
        record_auth_failure(reason="SESSION_REVOKED", metadata={"path": request.url.path})
        raise HTTPException(status_code=401, detail="Session revoked")

    expires_at = _ensure_utc_datetime(auth_session.session_expires_at)
    if expires_at <= time_now_utc():
        record_auth_failure(reason="SESSION_EXPIRED", metadata={"path": request.url.path})
        raise HTTPException(status_code=401, detail="Session expired")

    user = db.get(User, auth_session.user_id)
    if not user:
        record_auth_failure(reason="SESSION_USER_NOT_FOUND", metadata={"path": request.url.path})
        raise HTTPException(status_code=401, detail="Session user not found")

    return AuthContext(
        user_id=user.id,
        email=user.email,
        role=user.role,
        session_id=auth_session.id,
    )


def require_doctor(user: AuthContext = Depends(get_current_user)) -> AuthContext:
    if user.role != "DOCTOR":
        raise HTTPException(status_code=403, detail="Doctor role required")
    return user


def dev_auth_route_available(settings: Settings) -> bool:
    return settings.environment.lower() == "development" and settings.enable_dev_auth


def time_now_utc():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def _ensure_utc_datetime(value):
    if value.tzinfo is None:
        from datetime import timezone

        return value.replace(tzinfo=timezone.utc)
    from datetime import timezone

    return value.astimezone(timezone.utc)
