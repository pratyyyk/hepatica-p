from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ModelRegistry


class ModelPromotionError(RuntimeError):
    pass


@dataclass
class PromotionResult:
    action: str
    name: str
    version: str
    changed: bool
    deactivated_versions: list[str]
    active_versions: list[str]


def list_models(db: Session, *, name: str | None = None) -> list[ModelRegistry]:
    stmt = select(ModelRegistry)
    if name:
        stmt = stmt.where(ModelRegistry.name == name)
    stmt = stmt.order_by(ModelRegistry.name.asc(), ModelRegistry.created_at.desc(), ModelRegistry.version.desc())
    return list(db.scalars(stmt).all())


def activate_model_version(
    db: Session,
    *,
    name: str,
    version: str,
    exclusive: bool = True,
) -> PromotionResult:
    rows = list(
        db.scalars(
            select(ModelRegistry)
            .where(ModelRegistry.name == name)
            .order_by(ModelRegistry.created_at.desc(), ModelRegistry.version.desc())
        ).all()
    )
    if not rows:
        raise ModelPromotionError(f"No model versions found for name={name!r}")

    target = next((row for row in rows if row.version == version), None)
    if target is None:
        raise ModelPromotionError(f"Model version not found: {name}:{version}")

    deactivated: list[str] = []
    changed = False

    if not target.is_active:
        target.is_active = True
        changed = True

    if exclusive:
        for row in rows:
            if row.version == version:
                continue
            if row.is_active:
                row.is_active = False
                deactivated.append(row.version)
                changed = True

    db.flush()
    active_versions = [row.version for row in rows if row.is_active]
    return PromotionResult(
        action="activate",
        name=name,
        version=version,
        changed=changed,
        deactivated_versions=deactivated,
        active_versions=active_versions,
    )


def deactivate_model_version(
    db: Session,
    *,
    name: str,
    version: str,
    allow_zero_active: bool = False,
) -> PromotionResult:
    rows = list(
        db.scalars(
            select(ModelRegistry)
            .where(ModelRegistry.name == name)
            .order_by(ModelRegistry.created_at.desc(), ModelRegistry.version.desc())
        ).all()
    )
    if not rows:
        raise ModelPromotionError(f"No model versions found for name={name!r}")

    target = next((row for row in rows if row.version == version), None)
    if target is None:
        raise ModelPromotionError(f"Model version not found: {name}:{version}")

    active_count = sum(1 for row in rows if row.is_active)
    if target.is_active and active_count <= 1 and not allow_zero_active:
        raise ModelPromotionError(
            f"Refusing to deactivate the last active version for {name!r}. "
            "Use --allow-zero-active to force."
        )

    changed = False
    if target.is_active:
        target.is_active = False
        changed = True

    db.flush()
    active_versions = [row.version for row in rows if row.is_active]
    return PromotionResult(
        action="deactivate",
        name=name,
        version=version,
        changed=changed,
        deactivated_versions=[version] if changed else [],
        active_versions=active_versions,
    )
