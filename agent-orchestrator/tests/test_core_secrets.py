"""Tests for app.core.secrets (criptografia Fernet dos tokens de integrações).

Dono: be-integrations.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.core import secrets
from app.core.config import settings


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setattr(settings, "integrations_secret_key", Fernet.generate_key().decode())


def test_roundtrip_and_ciphertext_differs():
    token = "ghp_example123"
    enc = secrets.encrypt_secret(token)
    assert enc != token and "ghp_" not in enc
    assert secrets.decrypt_secret(enc) == token


def test_tampered_ciphertext_raises():
    with pytest.raises(secrets.SecretError):
        secrets.decrypt_secret("not-a-valid-token")


def test_missing_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "integrations_secret_key", "")
    with pytest.raises(secrets.SecretError, match="INTEGRATIONS_SECRET_KEY"):
        secrets.encrypt_secret("x")
