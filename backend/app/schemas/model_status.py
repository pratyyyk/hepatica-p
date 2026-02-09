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


class Stage1ModelStatus(BaseModel):
    enabled: bool
    registry: ModelRegistryStatus
    artifact_health: ArtifactHealthStatus


class Stage2ModelStatus(BaseModel):
    require_non_dev: bool
    registry: ModelRegistryStatus
    artifact_health: ArtifactHealthStatus
    temperature_artifact_path: str


class ModelStatusResponse(BaseModel):
    generated_at: datetime
    stage1: Stage1ModelStatus
    stage2: Stage2ModelStatus
