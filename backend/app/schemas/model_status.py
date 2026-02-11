from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ModelRegistryStatus(BaseModel):
    requested_name: str
    active_name: str | None
    active_version: str | None
    artifact_uri: str | None
    resolved_artifact_path: str
    active: bool


class ArtifactHealthStatus(BaseModel):
    strict_mode: bool
    ok: bool
    errors: list[str]
    severity: str
    ready_for_release: bool


class Stage1ModelStatus(BaseModel):
    enabled: bool
    registry: ModelRegistryStatus
    artifact_health: ArtifactHealthStatus
    ready_for_release: bool


class Stage2ModelStatus(BaseModel):
    require_non_dev: bool
    registry: ModelRegistryStatus
    artifact_health: ArtifactHealthStatus
    temperature_artifact_path: str
    ready_for_release: bool


class Stage3ModelStatus(BaseModel):
    enabled: bool
    require_non_dev: bool
    registry: ModelRegistryStatus
    artifact_health: ArtifactHealthStatus
    ready_for_release: bool


class ModelStatusResponse(BaseModel):
    generated_at: datetime
    stage1: Stage1ModelStatus
    stage2: Stage2ModelStatus
    stage3: Stage3ModelStatus
    severity: str
    ready_for_release: bool
