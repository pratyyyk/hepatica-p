from __future__ import annotations

from app.core.config import get_settings


def assert_status(response, expected_status: int) -> None:
    if response.status_code == expected_status:
        return
    method = response.request.method if response.request else "UNKNOWN"
    path = response.request.url.path if response.request else "UNKNOWN"
    raise AssertionError(
        f"Expected {expected_status}, got {response.status_code} for {method} {path}. "
        f"Response body: {response.text}"
    )


def dev_login(client, email: str = "doctor@example.com") -> dict[str, str]:
    resp = client.post("/api/v1/auth/dev-login", json={"email": email})
    assert_status(resp, 200)

    session_cookie = resp.cookies.get("hp_session") or client.cookies.get("hp_session")
    assert session_cookie, "Session cookie hp_session not found after dev-login"

    csrf = resp.cookies.get("hp_csrf") or client.cookies.get("hp_csrf")
    assert csrf, "CSRF cookie hp_csrf not found after dev-login"

    return {"x-csrf-token": csrf}


def test_unauthenticated_access_returns_401(client):
    resp = client.get("/api/v1/patients/nonexistent")
    assert_status(resp, 401)


def test_patient_create_and_read(client):
    csrf_headers = dev_login(client)

    payload = {
        "external_id": "P-001",
        "sex": "F",
        "age": 49,
        "bmi": 29.3,
        "type2dm": True,
    }
    create_resp = client.post("/api/v1/patients", json=payload, headers=csrf_headers)
    assert_status(create_resp, 201)
    patient = create_resp.json()
    assert patient["external_id"] == "P-001"

    get_resp = client.get(f"/api/v1/patients/{patient['id']}")
    assert_status(get_resp, 200)
    assert get_resp.json()["id"] == patient["id"]


def test_clinical_assessment_and_timeline(client):
    csrf_headers = dev_login(client)

    patient_resp = client.post(
        "/api/v1/patients",
        json={"external_id": "P-002", "sex": "M", "age": 58, "bmi": 31.2, "type2dm": True},
        headers=csrf_headers,
    )
    assert_status(patient_resp, 201)
    patient = patient_resp.json()

    clinical_resp = client.post(
        "/api/v1/assessments/clinical",
        json={
            "patient_id": patient["id"],
            "ast": 90,
            "alt": 70,
            "platelets": 130,
            "ast_uln": 40,
            "age": 58,
            "bmi": 31.2,
            "type2dm": True,
        },
        headers=csrf_headers,
    )
    assert_status(clinical_resp, 200)
    clinical = clinical_resp.json()
    assert clinical["risk_tier"] in {"LOW", "MODERATE", "HIGH"}

    timeline = client.get(f"/api/v1/patients/{patient['id']}/timeline")
    assert_status(timeline, 200)
    events = timeline.json()["events"]
    assert len(events) >= 2


def test_upload_url_validation(client):
    csrf_headers = dev_login(client)

    patient_resp = client.post(
        "/api/v1/patients",
        json={"external_id": "P-003", "sex": "F", "age": 42, "bmi": 22.4, "type2dm": False},
        headers=csrf_headers,
    )
    assert_status(patient_resp, 201)
    patient = patient_resp.json()

    invalid_resp = client.post(
        "/api/v1/scans/upload-url",
        json={
            "patient_id": patient["id"],
            "filename": "scan.exe",
            "content_type": "application/octet-stream",
            "byte_size": 1024,
        },
        headers=csrf_headers,
    )
    assert_status(invalid_resp, 422)


def test_knowledge_and_report_generation(client):
    csrf_headers = dev_login(client)

    patient_resp = client.post(
        "/api/v1/patients",
        json={"external_id": "P-004", "sex": "F", "age": 51, "bmi": 30.1, "type2dm": True},
        headers=csrf_headers,
    )
    assert_status(patient_resp, 201)
    patient = patient_resp.json()

    knowledge_resp = client.post(
        "/api/v1/knowledge/explain",
        json={"patient_id": patient["id"], "top_k": 3},
        headers=csrf_headers,
    )
    assert_status(knowledge_resp, 200)
    assert len(knowledge_resp.json()["blocks"]) == 5

    report_resp = client.post(
        "/api/v1/reports",
        json={"patient_id": patient["id"]},
        headers=csrf_headers,
    )
    assert_status(report_resp, 200)
    report = report_resp.json()
    assert report["report_id"]
    assert report["report_json"]["disclaimer"]


def test_csrf_missing_rejected(client):
    csrf_headers = dev_login(client)
    patient_resp = client.post(
        "/api/v1/patients",
        json={"external_id": "P-005", "sex": "F", "age": 39, "bmi": 24.0, "type2dm": False},
        headers=csrf_headers,
    )
    assert_status(patient_resp, 201)
    patient = patient_resp.json()

    bad_resp = client.post(
        "/api/v1/assessments/clinical",
        json={
            "patient_id": patient["id"],
            "ast": 60,
            "alt": 55,
            "platelets": 200,
            "ast_uln": 40,
            "age": 39,
            "bmi": 24,
            "type2dm": False,
        },
    )
    assert_status(bad_resp, 403)


def test_non_owner_cannot_access_patient(client):
    csrf_headers_user1 = dev_login(client, "doctor1@example.com")
    patient_resp = client.post(
        "/api/v1/patients",
        json={"external_id": "P-006", "sex": "F", "age": 48, "bmi": 27, "type2dm": False},
        headers=csrf_headers_user1,
    )
    assert_status(patient_resp, 201)
    patient = patient_resp.json()

    dev_login(client, "doctor2@example.com")
    resp = client.get(f"/api/v1/patients/{patient['id']}")
    assert_status(resp, 404)


def test_dev_login_blocked_when_not_enabled(client):
    cfg = get_settings()
    original = cfg.enable_dev_auth
    cfg.enable_dev_auth = False
    try:
        resp = client.post("/api/v1/auth/dev-login", json={"email": "doctor@example.com"})
        assert_status(resp, 404)
    finally:
        cfg.enable_dev_auth = original


def test_cors_allowed_and_disallowed_origins(client):
    allowed = client.options(
        "/api/v1/patients",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-csrf-token",
        },
    )
    assert_status(allowed, 200)
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"

    blocked = client.options(
        "/api/v1/patients",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-csrf-token",
        },
    )
    assert blocked.headers.get("access-control-allow-origin") != "https://evil.example"
