from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.api.v1.api import api_router
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.db.init_db import init_db
from app.services.audit import record_auth_failure

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", settings.csrf_header_name],
)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    record_auth_failure(
        reason="RATE_LIMIT_EXCEEDED",
        metadata={"path": request.url.path, "method": request.method},
    )
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded",
            "retry_hint": "Please retry after the rate limit window.",
        },
    )


@app.middleware("http")
async def csrf_protection_middleware(request: Request, call_next):
    mutating_methods = {"POST", "PUT", "PATCH", "DELETE"}
    exempt_paths = {
        "/api/v1/auth/login",
        "/api/v1/auth/callback",
        "/api/v1/auth/dev-login",
    }

    path = request.url.path
    if path.startswith("/api/v1") and request.method in mutating_methods and path not in exempt_paths:
        csrf_cookie = request.cookies.get(settings.csrf_cookie_name)
        csrf_header = request.headers.get(settings.csrf_header_name)
        if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
            record_auth_failure(
                reason="CSRF_VALIDATION_FAILED",
                metadata={"path": request.url.path, "method": request.method},
            )
            return JSONResponse(status_code=403, content={"detail": "CSRF validation failed"})

    return await call_next(request)

@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}


app.include_router(api_router)
