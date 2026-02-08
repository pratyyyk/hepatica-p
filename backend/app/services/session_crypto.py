from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utc_after_minutes(minutes: int) -> datetime:
    return utcnow() + timedelta(minutes=minutes)


def hash_value(value: str | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _fernet_key_from_secret(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_secret(value: str, encryption_key: str) -> str:
    f = Fernet(_fernet_key_from_secret(encryption_key))
    return f.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str, encryption_key: str) -> str:
    f = Fernet(_fernet_key_from_secret(encryption_key))
    return f.decrypt(value.encode("utf-8")).decode("utf-8")


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def generate_state() -> str:
    return secrets.token_urlsafe(24)


def generate_nonce() -> str:
    return secrets.token_urlsafe(24)


def generate_code_verifier() -> str:
    return secrets.token_urlsafe(72)


def code_challenge_s256(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
