from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.core.security import AuthContext


class _FakeFirebaseResponse:
    status_code = 200

    def json(self):
        return {"idToken": "fake-id-token", "refreshToken": "fake-refresh-token"}


def test_auth_login_reports_firebase_mode(client):
    cfg = get_settings()
    original = cfg.auth_provider
    cfg.auth_provider = "firebase"
    try:
        resp = client.get("/api/v1/auth/login")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["provider"] == "firebase"
        assert payload["login_endpoint"] == "/api/v1/auth/firebase-login"
    finally:
        cfg.auth_provider = original


def test_firebase_login_creates_session(client, monkeypatch):
    cfg = get_settings()
    original_provider = cfg.auth_provider
    original_project = cfg.firebase_project_id
    original_api_key = cfg.firebase_web_api_key

    cfg.auth_provider = "firebase"
    cfg.firebase_project_id = "demo-project"
    cfg.firebase_web_api_key = "demo-api-key"

    monkeypatch.setattr("app.api.v1.auth.requests.post", lambda *args, **kwargs: _FakeFirebaseResponse())
    monkeypatch.setattr(
        "app.api.v1.auth.verify_firebase_token",
        lambda token, settings: AuthContext(
            user_id="firebase-user-id",
            email="firebase-doctor@example.com",
            role="DOCTOR",
        ),
    )
    monkeypatch.setattr(
        "app.api.v1.auth.jwt.get_unverified_claims",
        lambda token: {"exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())},
    )

    try:
        resp = client.post(
            "/api/v1/auth/firebase-login",
            json={"email": "firebase-doctor@example.com", "password": "secret123"},
        )
        assert resp.status_code == 200
        assert (resp.cookies.get("hp_session") or client.cookies.get("hp_session")) is not None
        assert (resp.cookies.get("hp_csrf") or client.cookies.get("hp_csrf")) is not None
    finally:
        cfg.auth_provider = original_provider
        cfg.firebase_project_id = original_project
        cfg.firebase_web_api_key = original_api_key
