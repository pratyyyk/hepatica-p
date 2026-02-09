from __future__ import annotations

import os
from io import BytesIO
from urllib.parse import urlparse

from PIL import Image

from app.core.config import get_settings


def _assert_status(resp, expected: int) -> None:
    if resp.status_code == expected:
        return
    method = resp.request.method if resp.request else "UNKNOWN"
    path = resp.request.url.path if resp.request else "UNKNOWN"
    raise AssertionError(
        f"Expected {expected}, got {resp.status_code} for {method} {path}. Response: {resp.text}"
    )


def _dev_login(client, email: str) -> dict[str, str]:
    resp = client.post("/api/v1/auth/dev-login", json={"email": email})
    _assert_status(resp, 200)
    csrf = resp.cookies.get("hp_csrf") or client.cookies.get("hp_csrf")
    assert csrf, "CSRF cookie hp_csrf not found after dev-login"
    return {"x-csrf-token": csrf}


def _black_png_bytes(size: int = 256) -> bytes:
    img = Image.new("RGB", (size, size), (0, 0, 0))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _create_patient(client, csrf_headers: dict[str, str], external_id: str) -> dict:
    resp = client.post(
        "/api/v1/patients",
        json={"external_id": external_id, "sex": "F", "age": 45, "bmi": 28.0, "type2dm": False},
        headers=csrf_headers,
    )
    _assert_status(resp, 201)
    return resp.json()


def _upload_scan(client, csrf_headers: dict[str, str], patient_id: str, filename: str) -> str:
    ticket_resp = client.post(
        "/api/v1/scans/upload-url",
        json={
            "patient_id": patient_id,
            "filename": filename,
            "content_type": "image/png",
            "byte_size": 1234,
        },
        headers=csrf_headers,
    )
    _assert_status(ticket_resp, 200)
    ticket = ticket_resp.json()

    upload_path = urlparse(ticket["upload_url"]).path
    put_resp = client.put(
        upload_path,
        data=_black_png_bytes(),
        headers={**csrf_headers, "Content-Type": "image/png"},
    )
    _assert_status(put_resp, 200)
    return ticket["scan_asset_id"]


def test_stage2_quality_gate_strict_rejects(client, monkeypatch):
    monkeypatch.setenv("STAGE2_QUALITY_GATE", "strict")
    get_settings.cache_clear()

    csrf_headers = _dev_login(client, "doctor-quality-strict@example.com")
    patient = _create_patient(client, csrf_headers, "P-QUALITY-STRICT-001")
    scan_asset_id = _upload_scan(client, csrf_headers, patient["id"], "black.png")

    fibrosis_resp = client.post(
        "/api/v1/assessments/fibrosis",
        json={"patient_id": patient["id"], "scan_asset_id": scan_asset_id},
        headers=csrf_headers,
    )
    assert fibrosis_resp.status_code == 422
    payload = fibrosis_resp.json()
    assert payload["detail"]["reason"] == "Image quality check failed"
    assert "codes" in payload["detail"]
    assert "metrics" in payload["detail"]


def test_stage2_quality_gate_warn_allows_with_reason_codes(client, monkeypatch):
    monkeypatch.setenv("STAGE2_QUALITY_GATE", "warn")
    get_settings.cache_clear()

    csrf_headers = _dev_login(client, "doctor-quality-warn@example.com")
    patient = _create_patient(client, csrf_headers, "P-QUALITY-WARN-001")
    scan_asset_id = _upload_scan(client, csrf_headers, patient["id"], "black.png")

    fibrosis_resp = client.post(
        "/api/v1/assessments/fibrosis",
        json={"patient_id": patient["id"], "scan_asset_id": scan_asset_id},
        headers=csrf_headers,
    )
    _assert_status(fibrosis_resp, 200)
    payload = fibrosis_resp.json()

    qm = payload["quality_metrics"]
    assert qm["gate"] == "warn"
    assert qm["is_valid"] is False
    assert isinstance(qm["reason_codes"], list)
    assert "TOO_DARK" in qm["reason_codes"]

