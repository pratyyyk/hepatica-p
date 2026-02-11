from __future__ import annotations

from app.core.config import get_settings


def _assert_status(response, expected_status: int) -> None:
    if response.status_code == expected_status:
        return
    method = response.request.method if response.request else "UNKNOWN"
    path = response.request.url.path if response.request else "UNKNOWN"
    raise AssertionError(
        f"Expected {expected_status}, got {response.status_code} for {method} {path}. "
        f"Response body: {response.text}"
    )


def _dev_login(client, email: str = "doctor-stage3@example.com") -> dict[str, str]:
    resp = client.post("/api/v1/auth/dev-login", json={"email": email})
    _assert_status(resp, 200)
    csrf = resp.cookies.get("hp_csrf") or client.cookies.get("hp_csrf")
    assert csrf, "CSRF cookie hp_csrf not found after dev-login"
    return {"x-csrf-token": csrf}


def test_stage3_endpoints_happy_path(client):
    cfg = get_settings()
    original_stage3 = cfg.stage3_enabled
    cfg.stage3_enabled = True

    try:
        headers = _dev_login(client)
        patient_resp = client.post(
            "/api/v1/patients",
            json={"external_id": "P-STAGE3-001", "sex": "M", "age": 62, "bmi": 33.0, "type2dm": True},
            headers=headers,
        )
        _assert_status(patient_resp, 201)
        patient = patient_resp.json()

        clinical_resp = client.post(
            "/api/v1/assessments/clinical",
            json={
                "patient_id": patient["id"],
                "ast": 160,
                "alt": 80,
                "platelets": 105,
                "ast_uln": 40,
                "age": 62,
                "bmi": 33.0,
                "type2dm": True,
            },
            headers=headers,
        )
        _assert_status(clinical_resp, 200)

        stiff_resp = client.post(
            f"/api/v1/patients/{patient['id']}/stiffness",
            json={"measured_kpa": 24.5, "cap_dbm": 312.0, "source": "MEASURED"},
            headers=headers,
        )
        _assert_status(stiff_resp, 200)
        stiffness = stiff_resp.json()

        stage3_resp = client.post(
            "/api/v1/assessments/stage3",
            json={"patient_id": patient["id"], "stiffness_measurement_id": stiffness["id"]},
            headers=headers,
        )
        _assert_status(stage3_resp, 200)
        assessment = stage3_resp.json()
        assert assessment["risk_tier"] in {"LOW", "MODERATE", "HIGH", "CRITICAL"}
        assert 0.0 <= assessment["composite_risk_score"] <= 1.0
        assert assessment["feature_snapshot_json"]["stiffness_source"] in {"MEASURED", "PROXY"}

        history_resp = client.get(f"/api/v1/patients/{patient['id']}/stage3/history")
        _assert_status(history_resp, 200)
        history = history_resp.json()
        assert history["assessments"][0]["id"] == assessment["id"]

        explain_resp = client.get(f"/api/v1/patients/{patient['id']}/stage3/explainability")
        _assert_status(explain_resp, 200)
        explain = explain_resp.json()
        assert explain["stage3_assessment_id"] == assessment["id"]
        assert "positive" in explain["local_feature_contrib_json"]
        assert isinstance(explain["trend_points_json"], list)

        alerts_resp = client.get(f"/api/v1/patients/{patient['id']}/alerts")
        _assert_status(alerts_resp, 200)
        alerts = alerts_resp.json()
        assert "alerts" in alerts
        assert any(a["status"] == "open" for a in alerts["alerts"])

        # Re-run Stage 3 and ensure open alerts are deduplicated by alert_type.
        stage3_resp_2 = client.post(
            "/api/v1/assessments/stage3",
            json={"patient_id": patient["id"], "stiffness_measurement_id": stiffness["id"]},
            headers=headers,
        )
        _assert_status(stage3_resp_2, 200)
        alerts_resp_2 = client.get(f"/api/v1/patients/{patient['id']}/alerts?status=open")
        _assert_status(alerts_resp_2, 200)
        open_alerts = alerts_resp_2.json()["alerts"]
        types = [a["alert_type"] for a in open_alerts]
        assert len(types) == len(set(types)), "Open alert dedupe failed"

        first_alert = open_alerts[0]
        ack_resp = client.post(
            f"/api/v1/patients/{patient['id']}/alerts/{first_alert['id']}/status",
            json={"status": "ack"},
            headers=headers,
        )
        _assert_status(ack_resp, 200)
        assert ack_resp.json()["status"] == "ack"

        close_resp = client.post(
            f"/api/v1/patients/{patient['id']}/alerts/{first_alert['id']}/status",
            json={"status": "closed"},
            headers=headers,
        )
        _assert_status(close_resp, 200)
        assert close_resp.json()["status"] == "closed"
        assert close_resp.json()["resolved_at"] is not None

        timeline_resp = client.get(f"/api/v1/patients/{patient['id']}/timeline")
        _assert_status(timeline_resp, 200)
        event_types = {e["event_type"] for e in timeline_resp.json()["events"]}
        assert "STAGE3_ASSESSMENT_COMPLETED" in event_types
    finally:
        cfg.stage3_enabled = original_stage3


def test_stage3_feature_flag_returns_404_when_disabled(client):
    cfg = get_settings()
    original_stage3 = cfg.stage3_enabled
    cfg.stage3_enabled = False
    try:
        headers = _dev_login(client, email="doctor-stage3-flag@example.com")
        patient_resp = client.post(
            "/api/v1/patients",
            json={"external_id": "P-STAGE3-FLAG", "sex": "F", "age": 45, "bmi": 27.1, "type2dm": False},
            headers=headers,
        )
        _assert_status(patient_resp, 201)
        patient = patient_resp.json()

        resp = client.get(f"/api/v1/patients/{patient['id']}/alerts")
        _assert_status(resp, 404)
    finally:
        cfg.stage3_enabled = original_stage3
