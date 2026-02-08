from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import AuditLog


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
