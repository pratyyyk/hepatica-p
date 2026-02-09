#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///./smoke_hepatica.db")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("AUTH_MODE", "bff")
os.environ.setdefault("ENABLE_DEV_AUTH", "true")
os.environ.setdefault("SESSION_ENCRYPTION_KEY", "smoke-session-encryption-key")
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from app.core.config import get_settings

get_settings.cache_clear()

from app.db.base import Base
from app.db.session import engine
from app.main import app


def assert_status(response, expected_status: int, step: str) -> None:
    if response.status_code == expected_status:
        return
    method = response.request.method if response.request else "UNKNOWN"
    path = response.request.url.path if response.request else "UNKNOWN"
    raise RuntimeError(
        f"[{step}] expected {expected_status}, got {response.status_code} for {method} {path}. "
        f"response: {response.text}"
    )


def dev_login(client: TestClient, email: str) -> dict[str, str]:
    resp = client.post("/api/v1/auth/dev-login", json={"email": email})
    assert_status(resp, 200, "dev-login")
    csrf = resp.cookies.get("hp_csrf") or client.cookies.get("hp_csrf")
    if not csrf:
        raise RuntimeError("[dev-login] hp_csrf cookie missing")
    return {"x-csrf-token": csrf}


def run_smoke() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    external_id = f"SMOKE-{uuid.uuid4().hex[:8].upper()}"

    with TestClient(app) as client:
        headers = dev_login(client, "smoke-doctor@example.com")
        print("OK login/dev-login")

        create_resp = client.post(
            "/api/v1/patients",
            json={
                "external_id": external_id,
                "sex": "F",
                "age": 49,
                "bmi": 29.3,
                "type2dm": True,
            },
            headers=headers,
        )
        assert_status(create_resp, 201, "create-patient")
        patient = create_resp.json()

        read_resp = client.get(f"/api/v1/patients/{patient['id']}")
        assert_status(read_resp, 200, "read-patient")
        print("OK create/read patient")

        stage1_resp = client.post(
            "/api/v1/assessments/clinical",
            json={
                "patient_id": patient["id"],
                "ast": 90,
                "alt": 70,
                "platelets": 130,
                "ast_uln": 40,
                "age": 49,
                "bmi": 29.3,
                "type2dm": True,
            },
            headers=headers,
        )
        assert_status(stage1_resp, 200, "stage1-clinical")
        print("OK stage1 clinical assessment")

        invalid_upload_resp = client.post(
            "/api/v1/scans/upload-url",
            json={
                "patient_id": patient["id"],
                "filename": "scan.exe",
                "content_type": "application/octet-stream",
                "byte_size": 1024,
            },
            headers=headers,
        )
        assert_status(invalid_upload_resp, 422, "upload-invalid-file")
        print("OK upload-url invalid file -> 422")

        knowledge_resp = client.post(
            "/api/v1/knowledge/explain",
            json={"patient_id": patient["id"], "top_k": 3},
            headers=headers,
        )
        assert_status(knowledge_resp, 200, "knowledge-explain")

        report_resp = client.post(
            "/api/v1/reports",
            json={"patient_id": patient["id"]},
            headers=headers,
        )
        assert_status(report_resp, 200, "report-generation")
        print("OK knowledge + report generation")

        timeline_resp = client.get(f"/api/v1/patients/{patient['id']}/timeline")
        assert_status(timeline_resp, 200, "timeline-read")
        print("OK timeline read")


if __name__ == "__main__":
    run_smoke()
    print("Smoke flow passed.")
