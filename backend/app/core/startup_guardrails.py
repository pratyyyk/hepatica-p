from __future__ import annotations

from app.core.config import Settings


class StartupGuardrailError(RuntimeError):
    pass


WEAK_SESSION_KEYS = {
    "",
    "replace-with-strong-session-key",
    "changeme",
    "change-me",
    "change_me",
    "test-session-encryption-key",
    "smoke-session-encryption-key",
}


def validate_startup_security_guardrails(settings: Settings) -> None:
    if settings.is_local_dev:
        return

    key = (settings.session_encryption_key or "").strip()
    key_lower = key.lower()
    weak_values = WEAK_SESSION_KEYS | {value.lower() for value in WEAK_SESSION_KEYS}

    errors: list[str] = []
    if key_lower in weak_values:
        errors.append("SESSION_ENCRYPTION_KEY is using a known weak/default value")
    if len(key) < 32:
        errors.append("SESSION_ENCRYPTION_KEY must be at least 32 characters in non-dev")

    if errors:
        raise StartupGuardrailError("; ".join(errors))
