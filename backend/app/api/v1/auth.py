from __future__ import annotations

import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from jose import JWTError, jwt
from pydantic import ValidationError
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RequestUser, get_request_user
from app.core.config import Settings, get_settings
from app.core.rate_limit import limiter
from app.core.security import dev_auth_route_available, verify_cognito_token
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import AuthSessionResponse, DevLoginRequest, DevLoginResponse, LogoutResponse
from app.services.audit import write_audit_log
from app.services.auth_session import create_auth_session, revoke_session
from app.services.session_crypto import (
    code_challenge_s256,
    generate_code_verifier,
    generate_csrf_token,
    generate_nonce,
    generate_state,
)

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _normalized_cognito_domain(domain: str) -> str:
    trimmed = domain.strip()
    if not trimmed:
        raise HTTPException(status_code=500, detail="COGNITO_DOMAIN is not configured")
    if trimmed.startswith("http://") or trimmed.startswith("https://"):
        return trimmed.rstrip("/")
    return f"https://{trimmed.rstrip('/')}"


def _require_bff_settings(cfg: Settings) -> None:
    required = {
        "COGNITO_CLIENT_ID": cfg.cognito_client_id,
        "COGNITO_USER_POOL_ID": cfg.cognito_user_pool_id,
        "COGNITO_DOMAIN": cfg.cognito_domain,
        "OAUTH_REDIRECT_URI": cfg.oauth_redirect_uri,
        "SESSION_ENCRYPTION_KEY": cfg.session_encryption_key,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise HTTPException(status_code=500, detail=f"Missing auth config: {', '.join(missing)}")


def _set_auth_cookies(resp: JSONResponse | RedirectResponse, cfg: Settings, session_id: str, csrf_token: str) -> None:
    max_age = cfg.session_ttl_minutes * 60
    resp.set_cookie(
        key=cfg.session_cookie_name,
        value=session_id,
        httponly=True,
        secure=cfg.cookie_secure,
        samesite="lax",
        max_age=max_age,
        path="/",
    )
    resp.set_cookie(
        key=cfg.csrf_cookie_name,
        value=csrf_token,
        httponly=False,
        secure=cfg.cookie_secure,
        samesite="lax",
        max_age=max_age,
        path="/",
    )


@router.get("/login")
@limiter.limit(settings.rate_limit_auth_per_minute, key_func=get_remote_address)
def login(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    cfg: Settings = Depends(get_settings),
):
    _require_bff_settings(cfg)

    state = generate_state()
    nonce = generate_nonce()
    code_verifier = generate_code_verifier()
    challenge = code_challenge_s256(code_verifier)

    context = {
        "state": state,
        "nonce": nonce,
        "code_verifier": code_verifier,
        "iat": int(time.time()),
        "exp": int(time.time()) + 600,
    }
    encoded_context = jwt.encode(context, cfg.session_encryption_key, algorithm="HS256")

    base = _normalized_cognito_domain(cfg.cognito_domain)
    params = {
        "response_type": "code",
        "client_id": cfg.cognito_client_id,
        "redirect_uri": cfg.oauth_redirect_uri,
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
    }
    authorize_url = f"{base}/oauth2/authorize?{urlencode(params)}"

    write_audit_log(
        db,
        user_id=None,
        action="LOGIN_REDIRECT_INITIATED",
        resource_type="auth",
        resource_id=None,
        metadata={"ip": get_remote_address(request)},
    )
    db.commit()

    response = RedirectResponse(authorize_url, status_code=302)
    response.set_cookie(
        key=cfg.login_context_cookie_name,
        value=encoded_context,
        httponly=True,
        secure=cfg.cookie_secure,
        samesite="lax",
        max_age=600,
        path="/api/v1/auth",
    )
    return response


@router.get("/callback")
@limiter.limit(settings.rate_limit_auth_per_minute, key_func=get_remote_address)
def callback(
    request: Request,
    response: Response,
    code: str,
    state: str,
    db: Session = Depends(get_db),
    cfg: Settings = Depends(get_settings),
):
    _require_bff_settings(cfg)

    context_cookie = request.cookies.get(cfg.login_context_cookie_name)
    if not context_cookie:
        raise HTTPException(status_code=401, detail="Missing login context")

    try:
        context = jwt.decode(context_cookie, cfg.session_encryption_key, algorithms=["HS256"])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid login context") from exc

    if context.get("state") != state:
        raise HTTPException(status_code=401, detail="State mismatch")

    token_url = f"{_normalized_cognito_domain(cfg.cognito_domain)}/oauth2/token"
    token_resp = requests.post(
        token_url,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "authorization_code",
            "client_id": cfg.cognito_client_id,
            "code": code,
            "redirect_uri": cfg.oauth_redirect_uri,
            "code_verifier": context["code_verifier"],
        },
        timeout=10,
    )

    if token_resp.status_code >= 400:
        raise HTTPException(status_code=401, detail="Token exchange failed")

    token_payload = token_resp.json()
    id_token = token_payload.get("id_token")
    refresh_token = token_payload.get("refresh_token")
    if not id_token or not refresh_token:
        raise HTTPException(status_code=401, detail="Missing required tokens")

    claims = jwt.get_unverified_claims(id_token)
    if claims.get("nonce") != context.get("nonce"):
        raise HTTPException(status_code=401, detail="Nonce mismatch")

    auth_ctx = verify_cognito_token(id_token, cfg)

    user = db.scalar(select(User).where(User.email == auth_ctx.email))
    if user is None:
        user = User(email=auth_ctx.email, full_name=auth_ctx.email, role=auth_ctx.role)
        db.add(user)
        db.flush()
    else:
        user.role = auth_ctx.role

    exp = claims.get("exp")
    if exp is None:
        raise HTTPException(status_code=401, detail="id_token missing exp")
    id_token_expires_at = datetime.fromtimestamp(int(exp), tz=timezone.utc)

    auth_session = create_auth_session(
        db=db,
        user_id=user.id,
        refresh_token=refresh_token,
        id_token_expires_at=id_token_expires_at,
        settings=cfg,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    csrf_token = generate_csrf_token()

    write_audit_log(
        db,
        user_id=user.id,
        action="LOGIN_COMPLETED",
        resource_type="auth",
        resource_id=auth_session.id,
        metadata={"email": user.email},
    )
    db.commit()

    response = RedirectResponse(cfg.frontend_redirect_uri, status_code=302)
    _set_auth_cookies(response, cfg, auth_session.id, csrf_token)
    response.delete_cookie(cfg.login_context_cookie_name, path="/api/v1/auth")
    return response


@router.get("/session", response_model=AuthSessionResponse)
@limiter.limit(settings.rate_limit_auth_per_minute, key_func=get_remote_address)
def get_session(
    request: Request,
    response: Response,
    req_user: RequestUser = Depends(get_request_user),
    cfg: Settings = Depends(get_settings),
):
    csrf_token = request.cookies.get(cfg.csrf_cookie_name)
    return AuthSessionResponse(
        authenticated=True,
        user_id=req_user.db_user.id,
        email=req_user.db_user.email,
        role=req_user.db_user.role,
        csrf_token=csrf_token,
        csrf_header_name=cfg.csrf_header_name,
    )


@router.post("/logout", response_model=LogoutResponse)
@limiter.limit(settings.rate_limit_auth_per_minute, key_func=get_remote_address)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
    cfg: Settings = Depends(get_settings),
):
    session_id = request.cookies.get(cfg.session_cookie_name)
    if session_id:
        revoke_session(db, session_id)

    write_audit_log(
        db,
        user_id=req_user.db_user.id,
        action="LOGOUT",
        resource_type="auth",
        resource_id=session_id,
        metadata={},
    )
    db.commit()

    response = JSONResponse({"ok": True, "message": "Logged out"})
    response.delete_cookie(cfg.session_cookie_name, path="/")
    response.delete_cookie(cfg.csrf_cookie_name, path="/")
    response.delete_cookie(cfg.login_context_cookie_name, path="/api/v1/auth")
    return response


@router.post("/dev-login", response_model=DevLoginResponse)
@limiter.limit(settings.rate_limit_auth_per_minute, key_func=get_remote_address)
def dev_login(
    request: Request,
    response: Response,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    cfg: Settings = Depends(get_settings),
):
    if not dev_auth_route_available(cfg):
        raise HTTPException(status_code=404, detail="Not found")

    try:
        parsed_payload = DevLoginRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    user = db.scalar(select(User).where(User.email == parsed_payload.email))
    if user is None:
        user = User(
            email=parsed_payload.email,
            full_name=parsed_payload.full_name or parsed_payload.email,
            role="DOCTOR",
        )
        db.add(user)
        db.flush()

    auth_session = create_auth_session(
        db=db,
        user_id=user.id,
        refresh_token="dev-refresh-token",
        id_token_expires_at=datetime.now(timezone.utc),
        settings=cfg,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    write_audit_log(
        db,
        user_id=user.id,
        action="LOGIN_COMPLETED",
        resource_type="auth",
        resource_id=auth_session.id,
        metadata={"email": user.email, "mode": "dev-login"},
    )
    db.commit()

    csrf_token = generate_csrf_token()
    response = JSONResponse(
        DevLoginResponse(user_id=user.id, email=user.email, role=user.role).model_dump()
    )
    _set_auth_cookies(response, cfg, auth_session.id, csrf_token)
    return response
