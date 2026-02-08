from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.config import get_settings


settings = get_settings()


def user_or_ip_key(request: Request) -> str:
    session_id = request.cookies.get(settings.session_cookie_name)
    if session_id:
        return f"session:{session_id}"
    dev_user = request.headers.get("x-user-email")
    if dev_user:
        return f"dev:{dev_user}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=get_remote_address, headers_enabled=True)
