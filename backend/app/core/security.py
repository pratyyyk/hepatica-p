from __future__ import annotations

import json
import time
from functools import lru_cache
from typing import Any

import requests
from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt
from pydantic import BaseModel

from app.core.config import Settings, get_settings


class AuthContext(BaseModel):
    user_id: str
    email: str
    role: str = "DOCTOR"


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


def _extract_bearer(auth_header: str | None) -> str:
    if not auth_header:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing auth header")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth header")
    return token


def _verify_cognito_token(token: str, settings: Settings) -> AuthContext:
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
        groups = json.loads(groups_raw)
    else:
        groups = groups_raw
    role = "DOCTOR" if "DOCTOR" in groups or not groups else str(groups[0])
    return AuthContext(user_id=sub, email=email, role=role)


def get_current_user(
    authorization: str | None = Header(default=None),
    x_user_email: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> AuthContext:
    if settings.auth_disabled:
        if not x_user_email:
            raise HTTPException(status_code=401, detail="x-user-email header required in auth-disabled mode")
        return AuthContext(user_id=x_user_email, email=x_user_email, role="DOCTOR")
    token = _extract_bearer(authorization)
    return _verify_cognito_token(token, settings)


def require_doctor(user: AuthContext = Depends(get_current_user)) -> AuthContext:
    if user.role != "DOCTOR":
        raise HTTPException(status_code=403, detail="Doctor role required")
    return user
