from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    cognito_user_pool_id: str | None = None
    cognito_client_id: str | None = None
    cognito_region: str = "us-east-1"
    auth_disabled: bool = True

    bedrock_embedding_model_id: str = "amazon.titan-embed-text-v2:0"
    journals_path: Path = Path("/Users/praty/journals")
    local_image_root: Path = Path("/Users/praty/hepatica-p/data/Images")
    model_artifact_path: Path = Path("/Users/praty/hepatica-p/ml/artifacts/fibrosis_model.pt")
    temperature_artifact_path: Path = Path(
        "/Users/praty/hepatica-p/ml/artifacts/temperature_scaling.json"
    )

    max_upload_bytes: int = Field(default=25 * 1024 * 1024)
    presigned_expiration_seconds: int = Field(default=900)


@lru_cache
def get_settings() -> Settings:
    return Settings()
