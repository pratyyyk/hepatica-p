from __future__ import annotations


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


def test_patient_list_scoped_to_user_and_sorted_desc(client):
    headers_user1 = _dev_login(client, "doctor-list-1@example.com")

    create_a = client.post(
        "/api/v1/patients",
        json={"external_id": "P-LIST-001", "sex": "F", "age": 41, "bmi": 24.5, "type2dm": False},
        headers=headers_user1,
    )
    _assert_status(create_a, 201)

    create_b = client.post(
        "/api/v1/patients",
        json={"external_id": "P-LIST-002", "sex": "M", "age": 62, "bmi": 30.0, "type2dm": True},
        headers=headers_user1,
    )
    _assert_status(create_b, 201)
    b_id = create_b.json()["id"]

    list_resp = client.get("/api/v1/patients?limit=10&offset=0")
    _assert_status(list_resp, 200)
    rows = list_resp.json()
    assert len(rows) == 2
    # Created second -> should appear first with desc order by created_at.
    assert rows[0]["id"] == b_id

    headers_user2 = _dev_login(client, "doctor-list-2@example.com")
    create_c = client.post(
        "/api/v1/patients",
        json={"external_id": "P-LIST-003", "sex": "F", "age": 52, "bmi": 27.1, "type2dm": True},
        headers=headers_user2,
    )
    _assert_status(create_c, 201)

    list_user2 = client.get("/api/v1/patients?limit=10&offset=0")
    _assert_status(list_user2, 200)
    rows2 = list_user2.json()
    assert len(rows2) == 1
    assert rows2[0]["external_id"] == "P-LIST-003"

