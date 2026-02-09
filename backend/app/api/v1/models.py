from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.api.deps import RequestUser, get_request_user
from app.core.config import Settings, get_settings
from app.core.rate_limit import limiter, user_or_ip_key
from app.db.session import get_db
from app.schemas.model_status import (
    ArtifactHealthStatus,
    ModelRegistryStatus,
    ModelStatusResponse,
    Stage1ModelStatus,
    Stage2ModelStatus,
)
from app.services.fibrosis_inference import inspect_stage2_artifact_contract
from app.services.model_registry import get_active_model, resolve_local_artifact_path

router = APIRouter(prefix="/models", tags=["models"])
settings = get_settings()


@router.get("/status", response_model=ModelStatusResponse)
@limiter.limit(settings.rate_limit_read_per_user, key_func=user_or_ip_key)
@limiter.limit(settings.rate_limit_auth_per_minute, key_func=get_remote_address)
def get_model_status(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    req_user: RequestUser = Depends(get_request_user),
    cfg: Settings = Depends(get_settings),
):
    active_stage1 = get_active_model(db, cfg.stage1_registry_model_name)
    stage1_path = resolve_local_artifact_path(active_stage1, cfg.stage1_model_artifact_dir)
    stage1_errors: list[str] = []
    if cfg.stage1_ml_enabled:
        required_stage1_files = [
            stage1_path / "stage1_preprocessor.joblib",
            stage1_path / "stage1_classifier.joblib",
            stage1_path / "stage1_reg_probability.joblib",
        ]
        for path in required_stage1_files:
            if not path.exists():
                stage1_errors.append(f"missing Stage 1 artifact: {path}")
    stage1_registry = ModelRegistryStatus(
        requested_name=cfg.stage1_registry_model_name,
        active_name=active_stage1.name if active_stage1 else None,
        active_version=active_stage1.version if active_stage1 else None,
        artifact_uri=active_stage1.artifact_uri if active_stage1 else None,
        resolved_artifact_path=str(stage1_path),
        active=active_stage1 is not None,
    )
    stage1_status = Stage1ModelStatus(
        enabled=cfg.stage1_ml_enabled,
        registry=stage1_registry,
        artifact_health=ArtifactHealthStatus(
            strict_mode=not cfg.is_local_dev and cfg.stage1_require_model_non_dev,
            ok=not stage1_errors,
            errors=stage1_errors,
        ),
    )

    active_stage2 = get_active_model(db, cfg.stage2_registry_model_name)
    stage2_path = resolve_local_artifact_path(active_stage2, cfg.model_artifact_path)
    stage2_errors = inspect_stage2_artifact_contract(
        model_artifact_path=stage2_path,
        temperature_artifact_path=cfg.temperature_artifact_path,
    )
    stage2_registry = ModelRegistryStatus(
        requested_name=cfg.stage2_registry_model_name,
        active_name=active_stage2.name if active_stage2 else None,
        active_version=active_stage2.version if active_stage2 else None,
        artifact_uri=active_stage2.artifact_uri if active_stage2 else None,
        resolved_artifact_path=str(stage2_path),
        active=active_stage2 is not None,
    )
    stage2_status = Stage2ModelStatus(
        require_non_dev=cfg.stage2_require_model_non_dev,
        registry=stage2_registry,
        artifact_health=ArtifactHealthStatus(
            strict_mode=not cfg.is_local_dev and cfg.stage2_require_model_non_dev,
            ok=not stage2_errors,
            errors=stage2_errors,
        ),
        temperature_artifact_path=str(cfg.temperature_artifact_path),
    )

    return ModelStatusResponse(
        generated_at=datetime.now(timezone.utc),
        stage1=stage1_status,
        stage2=stage2_status,
    )
