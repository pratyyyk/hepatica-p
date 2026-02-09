from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import ScanAsset
from app.db.session import engine


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


def test_local_upload_requires_csrf(client):
    csrf_headers = _dev_login(client, "doctor-csrf@example.com")

    patient_resp = client.post(
        "/api/v1/patients",
        json={"external_id": "P-CSRF-001", "sex": "F", "age": 40, "bmi": 25.0, "type2dm": False},
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
            "byte_size": 12,
        },
        headers=csrf_headers,
    )
    _assert_status(ticket_resp, 200)
    ticket = ticket_resp.json()

    # Missing CSRF header -> blocked by middleware.
    put_resp = client.put(f"/api/v1/scans/upload/{ticket['scan_asset_id']}", data=b"1234", headers={"Content-Type": "image/png"})
    assert put_resp.status_code == 403


def test_local_upload_rejects_path_outside_upload_dir(client):
    csrf_headers = _dev_login(client, "doctor-path@example.com")

    patient_resp = client.post(
        "/api/v1/patients",
        json={"external_id": "P-PATH-001", "sex": "M", "age": 55, "bmi": 29.0, "type2dm": True},
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
            "byte_size": 12,
        },
        headers=csrf_headers,
    )
    _assert_status(ticket_resp, 200)
    ticket = ticket_resp.json()

    with Session(engine) as db:
        scan = db.get(ScanAsset, ticket["scan_asset_id"])
        assert scan is not None
        scan.object_key = "/etc/passwd"
        db.commit()

    put_resp = client.put(
        f"/api/v1/scans/upload/{ticket['scan_asset_id']}",
        data=b"1234",
        headers={**csrf_headers, "Content-Type": "image/png"},
    )
    _assert_status(put_resp, 422)

