from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import AuditLog
from app.db.session import SessionLocal


def write_audit_log(
    db: Session,
    *,
    user_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    metadata: dict,
) -> AuditLog:
    log = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata_json=metadata,
    )
    db.add(log)
    db.flush()
    return log


def record_auth_failure(*, reason: str, metadata: dict | None = None) -> None:
    try:
        with SessionLocal() as db:
            write_audit_log(
                db,
                user_id=None,
                action="AUTH_FAILURE",
                resource_type="auth",
                resource_id=None,
                metadata={"reason": reason, **(metadata or {})},
            )
            db.commit()
    except Exception:
        # Authentication guards must never fail due to audit write issues.
        pass
