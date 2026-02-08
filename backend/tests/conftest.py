import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite:///./test_hepatica.db"
os.environ["AUTH_DISABLED"] = "true"

from app.db.base import Base
from app.db.session import engine
from app.main import app

TEST_DB_PATH = Path("test_hepatica.db")


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return {"x-user-email": "doctor@example.com"}


@pytest.fixture(scope="session", autouse=True)
def cleanup_db_file():
    yield
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
