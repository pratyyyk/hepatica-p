#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EVIDENCE_DB_PATH = ROOT / f"smoke_hepatica_evidence_{os.getpid()}_{uuid.uuid4().hex}.db"
os.environ.setdefault("DATABASE_URL", f"sqlite:///{EVIDENCE_DB_PATH}")
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


@dataclass
class StepEvidence:
    step: str
    started_at: str
    ended_at: str
    method: str
    path: str
    expected_status: int
    actual_status: int
    ok: bool
    request_body: Any | None
    response_body: Any | str | None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _response_body(response) -> Any | str | None:
    try:
        return response.json()
    except Exception:
        text = response.text
        return text if text else None


def _record_step(
    *,
    step: str,
    response,
    expected_status: int,
    started_at: str,
    request_body: Any | None,
) -> StepEvidence:
    ended_at = _utc_now()
    request = response.request
    return StepEvidence(
        step=step,
        started_at=started_at,
        ended_at=ended_at,
        method=request.method if request else "UNKNOWN",
        path=request.url.path if request else "UNKNOWN",
        expected_status=expected_status,
        actual_status=response.status_code,
        ok=response.status_code == expected_status,
        request_body=request_body,
        response_body=_response_body(response),
    )


def _dev_login(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/auth/dev-login", json={"email": "evidence-doctor@example.com"})
    if response.status_code != 200:
        raise RuntimeError(f"dev-login failed: {response.status_code} {response.text}")
    csrf = response.cookies.get("hp_csrf") or client.cookies.get("hp_csrf")
    if not csrf:
        raise RuntimeError("dev-login failed: hp_csrf missing")
    return {"x-csrf-token": csrf}


def run_evidence(out_json: Path, out_md: Path) -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    external_id = f"EVID-{uuid.uuid4().hex[:8].upper()}"
    steps: list[StepEvidence] = []

    with TestClient(app) as client:
        headers = _dev_login(client)

        create_body = {
            "external_id": external_id,
            "sex": "F",
            "age": 49,
            "bmi": 29.3,
            "type2dm": True,
        }
        started = _utc_now()
        create_resp = client.post("/api/v1/patients", json=create_body, headers=headers)
        create_step = _record_step(
            step="create_patient",
            response=create_resp,
            expected_status=201,
            started_at=started,
            request_body=create_body,
        )
        steps.append(create_step)
        if not create_step.ok:
            raise RuntimeError(f"create_patient failed: {create_resp.text}")
        patient = create_resp.json()

        started = _utc_now()
        read_resp = client.get(f"/api/v1/patients/{patient['id']}")
        steps.append(
            _record_step(
                step="read_patient",
                response=read_resp,
                expected_status=200,
                started_at=started,
                request_body=None,
            )
        )

        stage1_body = {
            "patient_id": patient["id"],
            "ast": 90,
            "alt": 70,
            "platelets": 130,
            "ast_uln": 40,
            "age": 49,
            "bmi": 29.3,
            "type2dm": True,
        }
        started = _utc_now()
        stage1_resp = client.post("/api/v1/assessments/clinical", json=stage1_body, headers=headers)
        steps.append(
            _record_step(
                step="stage1_clinical_assessment",
                response=stage1_resp,
                expected_status=200,
                started_at=started,
                request_body=stage1_body,
            )
        )

        invalid_upload_body = {
            "patient_id": patient["id"],
            "filename": "scan.exe",
            "content_type": "application/octet-stream",
            "byte_size": 1024,
        }
        started = _utc_now()
        invalid_upload_resp = client.post(
            "/api/v1/scans/upload-url",
            json=invalid_upload_body,
            headers=headers,
        )
        steps.append(
            _record_step(
                step="upload_invalid_file",
                response=invalid_upload_resp,
                expected_status=422,
                started_at=started,
                request_body=invalid_upload_body,
            )
        )

        knowledge_body = {"patient_id": patient["id"], "top_k": 3}
        started = _utc_now()
        knowledge_resp = client.post("/api/v1/knowledge/explain", json=knowledge_body, headers=headers)
        steps.append(
            _record_step(
                step="knowledge_explain",
                response=knowledge_resp,
                expected_status=200,
                started_at=started,
                request_body=knowledge_body,
            )
        )

        report_body = {"patient_id": patient["id"]}
        started = _utc_now()
        report_resp = client.post("/api/v1/reports", json=report_body, headers=headers)
        steps.append(
            _record_step(
                step="report_generation",
                response=report_resp,
                expected_status=200,
                started_at=started,
                request_body=report_body,
            )
        )

        started = _utc_now()
        timeline_resp = client.get(f"/api/v1/patients/{patient['id']}/timeline")
        steps.append(
            _record_step(
                step="timeline_read",
                response=timeline_resp,
                expected_status=200,
                started_at=started,
                request_body=None,
            )
        )

    all_ok = all(step.ok for step in steps)
    payload = {
        "generated_at": _utc_now(),
        "all_ok": all_ok,
        "steps": [asdict(step) for step in steps],
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2))

    lines = [
        "# UAT Smoke Evidence",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- all_ok: `{all_ok}`",
        "",
        "| step | expected | actual | ok |",
        "|---|---:|---:|---|",
    ]
    for step in steps:
        lines.append(f"| {step.step} | {step.expected_status} | {step.actual_status} | {step.ok} |")
    out_md.write_text("\n".join(lines) + "\n")

    if not all_ok:
        raise RuntimeError(f"One or more smoke evidence steps failed. See {out_json}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run smoke flow and persist evidence artifacts.")
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path("artifacts/uat/uat_evidence.json"),
        help="Output JSON path.",
    )
    parser.add_argument(
        "--out-md",
        type=Path,
        default=Path("artifacts/uat/uat_evidence.md"),
        help="Output Markdown summary path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        run_evidence(out_json=args.out_json, out_md=args.out_md)
        print(f"UAT evidence written: {args.out_json}")
        print(f"UAT summary written: {args.out_md}")
    finally:
        try:
            if EVIDENCE_DB_PATH.exists():
                EVIDENCE_DB_PATH.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    main()
