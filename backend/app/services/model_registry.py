from __future__ import annotations

from pathlib import Path

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import ModelRegistry


def get_active_model(db: Session, model_name: str) -> ModelRegistry | None:
    return db.scalar(
        select(ModelRegistry)
        .where(
            ModelRegistry.name == model_name,
            ModelRegistry.is_active.is_(True),
        )
        .order_by(desc(ModelRegistry.created_at), desc(ModelRegistry.version))
        .limit(1)
    )


def format_model_version(
    model: ModelRegistry | None,
    default_name: str,
    default_version: str,
) -> str:
    if model is None:
        return f"{default_name}:{default_version}"
    return f"{model.name}:{model.version}"


def resolve_local_artifact_path(
    model: ModelRegistry | None,
    default_path: Path,
) -> Path:
    if model is None:
        return default_path

    artifact_uri = (model.artifact_uri or "").strip()
    if artifact_uri.startswith("file://"):
        resolved = artifact_uri[len("file://") :]
        if resolved:
            return Path(resolved)
    if artifact_uri.startswith("/"):
        return Path(artifact_uri)

    return default_path
