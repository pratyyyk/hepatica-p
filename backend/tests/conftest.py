from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///./test_hepatica.db"
os.environ["ENVIRONMENT"] = "development"
os.environ["AUTH_MODE"] = "bff"
os.environ["ENABLE_DEV_AUTH"] = "true"
os.environ["SESSION_ENCRYPTION_KEY"] = "test-session-encryption-key"
os.environ["CORS_ALLOWED_ORIGINS"] = "http://localhost:3000"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["STAGE3_ENABLED"] = "false"

from app.core.config import get_settings
get_settings.cache_clear()
from app.core.rate_limit import limiter
from app.db.base import Base
from app.db.session import engine
from app.main import app

TEST_DB_PATH = Path("test_hepatica.db")


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    storage = getattr(limiter, "_storage", None)
    if storage and hasattr(storage, "reset"):
        storage.reset()
    yield


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session", autouse=True)
def cleanup_db_file():
    yield
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
