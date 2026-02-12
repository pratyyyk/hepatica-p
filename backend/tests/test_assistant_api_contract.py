from __future__ import annotations


def _assert_status(response, expected_status: int) -> None:
    if response.status_code == expected_status:
        return
    method = response.request.method if response.request else "UNKNOWN"
    path = response.request.url.path if response.request else "UNKNOWN"
    raise AssertionError(
        f"Expected {expected_status}, got {response.status_code} for {method} {path}. "
        f"Response body: {response.text}"
    )


def _dev_login(client, email: str = "doctor-assistant@example.com") -> dict[str, str]:
    resp = client.post("/api/v1/auth/dev-login", json={"email": email})
    _assert_status(resp, 200)
    csrf = resp.cookies.get("hp_csrf") or client.cookies.get("hp_csrf")
    assert csrf, "CSRF cookie hp_csrf not found after dev-login"
    return {"x-csrf-token": csrf}


def test_assistant_chat_with_patient_context(client):
    headers = _dev_login(client)

    patient_resp = client.post(
        "/api/v1/patients",
        json={"external_id": "P-ASSIST-001", "sex": "F", "age": 52, "bmi": 30.4, "type2dm": True},
        headers=headers,
    )
    _assert_status(patient_resp, 201)
    patient = patient_resp.json()

    clinical_resp = client.post(
        "/api/v1/assessments/clinical",
        json={
            "patient_id": patient["id"],
            "ast": 96,
            "alt": 71,
            "platelets": 142,
            "ast_uln": 40,
            "age": 52,
            "bmi": 30.4,
            "type2dm": True,
        },
        headers=headers,
    )
    _assert_status(clinical_resp, 200)

    chat_resp = client.post(
        "/api/v1/assistant/chat",
        json={
            "patient_id": patient["id"],
            "message": "Give me a concise risk summary and next steps",
        },
        headers=headers,
    )
    _assert_status(chat_resp, 200)
    payload = chat_resp.json()

    assert payload["patient_id"] == patient["id"]
    assert "Patient P-ASSIST-001 summary" in payload["reply"]
    assert payload["patient_summary"]["external_id"] == "P-ASSIST-001"
    assert payload["patient_summary"]["stage1_risk_tier"] in {"LOW", "MODERATE", "HIGH"}
    assert len(payload["suggestions"]) >= 1


def test_assistant_chat_without_patient_context(client):
    headers = _dev_login(client, email="doctor-assistant-no-patient@example.com")

    chat_resp = client.post(
        "/api/v1/assistant/chat",
        json={"message": "How can you help me?"},
        headers=headers,
    )
    _assert_status(chat_resp, 200)
    payload = chat_resp.json()

    assert payload["patient_id"] is None
    assert payload["patient_summary"] is None
    assert "select a patient" in payload["reply"].lower()
    assert len(payload["suggestions"]) >= 1


def test_assistant_chat_enforces_patient_ownership(client):
    headers_user1 = _dev_login(client, email="doctor-assistant-owner@example.com")

    patient_resp = client.post(
        "/api/v1/patients",
        json={"external_id": "P-ASSIST-OWN", "sex": "M", "age": 49, "bmi": 27.0, "type2dm": False},
        headers=headers_user1,
    )
    _assert_status(patient_resp, 201)
    patient = patient_resp.json()

    headers_user2 = _dev_login(client, email="doctor-assistant-other@example.com")
    denied = client.post(
        "/api/v1/assistant/chat",
        json={"patient_id": patient["id"], "message": "Summarize this patient"},
        headers=headers_user2,
    )
    _assert_status(denied, 404)
