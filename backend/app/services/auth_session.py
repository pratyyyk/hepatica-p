from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import AuthSession
from app.services.session_crypto import encrypt_secret, hash_value, utc_after_minutes, utcnow


def create_auth_session(
    *,
    db: Session,
    user_id: str,
    refresh_token: str,
    id_token_expires_at: datetime,
    settings: Settings,
    ip_address: str | None,
    user_agent: str | None,
) -> AuthSession:
    session = AuthSession(
        user_id=user_id,
        refresh_token_encrypted=encrypt_secret(refresh_token, settings.session_encryption_key),
        id_token_expires_at=id_token_expires_at,
        session_expires_at=utc_after_minutes(settings.session_ttl_minutes),
        revoked_at=None,
        last_seen_at=utcnow(),
        ip_hash=hash_value(ip_address),
        user_agent_hash=hash_value(user_agent),
    )
    db.add(session)
    db.flush()
    return session


def get_active_session(db: Session, session_id: str) -> AuthSession | None:
    row = db.scalar(select(AuthSession).where(AuthSession.id == session_id))
    if row is None:
        return None
    now = utcnow()
    if row.revoked_at is not None:
        return None
    expires_at = _ensure_utc_datetime(row.session_expires_at)
    if expires_at <= now:
        return None
    return row


def revoke_session(db: Session, session_id: str) -> AuthSession | None:
    row = db.scalar(select(AuthSession).where(AuthSession.id == session_id))
    if row is None:
        return None
    if row.revoked_at is None:
        row.revoked_at = utcnow()
    db.flush()
    return row


def _ensure_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        from datetime import timezone

        return value.replace(tzinfo=timezone.utc)
    from datetime import timezone

    return value.astimezone(timezone.utc)
