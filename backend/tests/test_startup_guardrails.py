from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.startup_guardrails import StartupGuardrailError, validate_startup_security_guardrails


def test_guardrail_allows_development_with_weak_key():
    settings = Settings(environment="development", session_encryption_key="replace-with-strong-session-key")
    validate_startup_security_guardrails(settings)


def test_guardrail_rejects_default_key_in_non_dev():
    settings = Settings(environment="production", session_encryption_key="replace-with-strong-session-key")
    with pytest.raises(StartupGuardrailError, match="known weak/default value"):
        validate_startup_security_guardrails(settings)


def test_guardrail_rejects_short_key_in_non_dev():
    settings = Settings(environment="staging", session_encryption_key="short-key")
    with pytest.raises(StartupGuardrailError, match="at least 32 characters"):
        validate_startup_security_guardrails(settings)


def test_guardrail_accepts_strong_key_in_non_dev():
    strong_key = "hp_live_7fe9c95a8c2a4e5e87d35500a9de95e2"
    settings = Settings(environment="production", session_encryption_key=strong_key)
    validate_startup_security_guardrails(settings)
