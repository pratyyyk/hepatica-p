from __future__ import annotations

from io import BytesIO
from urllib.parse import urlparse

import numpy as np
from PIL import Image


def _assert_status(resp, expected: int) -> None:
    if resp.status_code == expected:
        return
    method = resp.request.method if resp.request else "UNKNOWN"
    path = resp.request.url.path if resp.request else "UNKNOWN"
    raise AssertionError(
        f"Expected {expected}, got {resp.status_code} for {method} {path}. Response: {resp.text}"
    )


def _dev_login(client, email: str = "doctor@example.com") -> dict[str, str]:
    resp = client.post("/api/v1/auth/dev-login", json={"email": email})
    _assert_status(resp, 200)
    csrf = resp.cookies.get("hp_csrf") or client.cookies.get("hp_csrf")
    assert csrf, "CSRF cookie hp_csrf not found after dev-login"
    return {"x-csrf-token": csrf}


def _noise_png_bytes(seed: int = 0) -> bytes:
    rng = np.random.RandomState(seed)
    arr = rng.randint(0, 255, (384, 384, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_local_upload_then_stage2_inference(client):
    csrf_headers = _dev_login(client)

    patient_resp = client.post(
        "/api/v1/patients",
        json={"external_id": "P-LOCAL-001", "sex": "F", "age": 49, "bmi": 29.3, "type2dm": True},
        headers=csrf_headers,
    )
    _assert_status(patient_resp, 201)
    patient = patient_resp.json()

    ticket_resp = client.post(
        "/api/v1/scans/upload-url",
        json={
            "patient_id": patient["id"],
            "filename": "scan.png",
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
        data=_noise_png_bytes(),
        headers={**csrf_headers, "Content-Type": "image/png"},
    )
    _assert_status(put_resp, 200)
    assert put_resp.json()["ok"] is True

    fibrosis_resp = client.post(
        "/api/v1/assessments/fibrosis",
        json={"patient_id": patient["id"], "scan_asset_id": ticket["scan_asset_id"]},
        headers=csrf_headers,
    )
    _assert_status(fibrosis_resp, 200)
    payload = fibrosis_resp.json()
    assert payload["prediction_id"]
    assert payload["top1"]["stage"] in {"F0", "F1", "F2", "F3", "F4"}


def test_report_pdf_endpoint_serves_bytes(client):
    csrf_headers = _dev_login(client, "doctor-report@example.com")

    patient_resp = client.post(
        "/api/v1/patients",
        json={"external_id": "P-LOCAL-002", "sex": "M", "age": 58, "bmi": 31.2, "type2dm": True},
        headers=csrf_headers,
    )
    _assert_status(patient_resp, 201)
    patient = patient_resp.json()

    report_resp = client.post(
        "/api/v1/reports",
        json={"patient_id": patient["id"]},
        headers=csrf_headers,
    )
    _assert_status(report_resp, 200)
    report = report_resp.json()
    assert report["report_id"]
    assert report["pdf_download_url"]

    pdf_path = urlparse(report["pdf_download_url"]).path
    pdf_resp = client.get(pdf_path)
    _assert_status(pdf_resp, 200)
    assert "application/pdf" in (pdf_resp.headers.get("content-type") or "")
    assert len(pdf_resp.content) > 200
