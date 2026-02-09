from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Hepatica API"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False

    database_url: str = "sqlite:///./hepatica.db"
    aws_region: str = "us-east-1"

    s3_upload_bucket: str = "hepatica-scans"
    s3_report_bucket: str = "hepatica-reports"

    auth_mode: Literal["bff", "dev_header"] = "bff"
    auth_provider: Literal["firebase", "cognito"] = "firebase"
    enable_dev_auth: bool = False

    # Backward compatibility (legacy). No longer used for primary auth decisions.
    auth_disabled: bool = False

    cognito_user_pool_id: str | None = None
    cognito_client_id: str | None = None
    cognito_region: str = "us-east-1"
    cognito_domain: str = ""
    firebase_project_id: str = ""
    firebase_web_api_key: str = ""
    firebase_jwks_url: str = (
        "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
    )

    oauth_redirect_uri: str = "http://localhost:8000/api/v1/auth/callback"
    oauth_logout_redirect_uri: str = "http://localhost:3000"
    frontend_redirect_uri: str = "http://localhost:3000"

    session_ttl_minutes: int = 480
    session_cookie_name: str = "hp_session"
    csrf_cookie_name: str = "hp_csrf"
    csrf_header_name: str = "x-csrf-token"
    login_context_cookie_name: str = "hp_login_ctx"
    session_encryption_key: str = "replace-with-strong-session-key"

    cors_allowed_origins: str = "http://localhost:3000"

    rate_limit_auth_per_minute: str = "20/minute"
    rate_limit_mutating_per_user: str = "60/minute"
    rate_limit_mutating_per_ip: str = "120/minute"
    rate_limit_read_per_user: str = "180/minute"
    rate_limit_enabled: bool = True

    stage1_ml_enabled: bool = True
    stage1_require_model_non_dev: bool = True
    stage1_registry_model_name: str = "clinical-stage1-gbdt"
    stage1_model_artifact_dir: Path = REPO_ROOT / "ml" / "artifacts" / "stage1"

    stage2_require_model_non_dev: bool = True
    stage2_registry_model_name: str = "fibrosis-efficientnet-b3"

    bedrock_embedding_model_id: str = "amazon.titan-embed-text-v2:0"
    journals_path: Path = Path("/Users/praty/journals")
    local_image_root: Path = REPO_ROOT / "data" / "Images"
    model_artifact_path: Path = REPO_ROOT / "ml" / "artifacts" / "fibrosis_model.pt"
    temperature_artifact_path: Path = Path(
        REPO_ROOT / "ml" / "artifacts" / "temperature_scaling.json"
    )

    max_upload_bytes: int = Field(default=25 * 1024 * 1024)
    presigned_expiration_seconds: int = Field(default=900)

    upload_mode: Literal["auto", "local", "s3"] = "auto"
    local_storage_dir: Path = REPO_ROOT / "backend" / "artifacts"

    @property
    def is_local_dev(self) -> bool:
        return self.environment.lower() == "development"

    @property
    def resolved_upload_mode(self) -> Literal["local", "s3"]:
        if self.upload_mode != "auto":
            return self.upload_mode
        return "local" if self.is_local_dev else "s3"

    @property
    def local_storage_dir_resolved(self) -> Path:
        path = Path(self.local_storage_dir)
        if path.is_absolute():
            return path
        # If a relative path is provided via env, make it repo-root relative.
        return (REPO_ROOT / path).resolve()

    @property
    def local_upload_dir(self) -> Path:
        return self.local_storage_dir_resolved / "uploads"

    @property
    def local_report_dir(self) -> Path:
        return self.local_storage_dir_resolved / "reports"

    @property
    def cookie_secure(self) -> bool:
        return not self.is_local_dev

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        raw = self.cors_allowed_origins.strip()
        if not raw:
            return []
        if raw.startswith("["):
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                raise ValueError("CORS_ALLOWED_ORIGINS JSON must be an array")
            return [str(x) for x in parsed]
        return [part.strip() for part in raw.split(",") if part.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
