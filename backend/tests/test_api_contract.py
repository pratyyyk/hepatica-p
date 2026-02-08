def test_patient_create_and_read(client, auth_headers):
    payload = {
        "external_id": "P-001",
        "sex": "F",
        "age": 49,
        "bmi": 29.3,
        "type2dm": True,
    }
    create_resp = client.post("/api/v1/patients", json=payload, headers=auth_headers)
    assert create_resp.status_code == 201
    patient = create_resp.json()
    assert patient["external_id"] == "P-001"

    get_resp = client.get(f"/api/v1/patients/{patient['id']}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == patient["id"]


def test_clinical_assessment_and_timeline(client, auth_headers):
    patient = client.post(
        "/api/v1/patients",
        json={"external_id": "P-002", "sex": "M", "age": 58, "bmi": 31.2, "type2dm": True},
        headers=auth_headers,
    ).json()

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
        headers=auth_headers,
    )
    assert clinical_resp.status_code == 200
    clinical = clinical_resp.json()
    assert clinical["risk_tier"] in {"LOW", "MODERATE", "HIGH"}

    timeline = client.get(f"/api/v1/patients/{patient['id']}/timeline", headers=auth_headers)
    assert timeline.status_code == 200
    events = timeline.json()["events"]
    assert len(events) >= 2


def test_upload_url_validation(client, auth_headers):
    patient = client.post(
        "/api/v1/patients",
        json={"external_id": "P-003", "sex": "F", "age": 42, "bmi": 22.4, "type2dm": False},
        headers=auth_headers,
    ).json()

    invalid_resp = client.post(
        "/api/v1/scans/upload-url",
        json={
            "patient_id": patient["id"],
            "filename": "scan.exe",
            "content_type": "application/octet-stream",
            "byte_size": 1024,
        },
        headers=auth_headers,
    )
    assert invalid_resp.status_code == 422


def test_knowledge_and_report_generation(client, auth_headers):
    patient = client.post(
        "/api/v1/patients",
        json={"external_id": "P-004", "sex": "F", "age": 51, "bmi": 30.1, "type2dm": True},
        headers=auth_headers,
    ).json()

    knowledge_resp = client.post(
        "/api/v1/knowledge/explain",
        json={"patient_id": patient["id"], "top_k": 3},
        headers=auth_headers,
    )
    assert knowledge_resp.status_code == 200
    assert len(knowledge_resp.json()["blocks"]) == 5

    report_resp = client.post(
        "/api/v1/reports",
        json={"patient_id": patient["id"]},
        headers=auth_headers,
    )
    assert report_resp.status_code == 200
    report = report_resp.json()
    assert report["report_id"]
    assert report["report_json"]["disclaimer"]
