"""Criptografia simétrica (Fernet) dos tokens das integrações Git."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class SecretError(Exception):
    """Chave ausente ou segredo corrompido."""


def _fernet() -> Fernet:
    key = settings.integrations_secret_key
    if not key:
        raise SecretError("INTEGRATIONS_SECRET_KEY não configurada")
    return Fernet(key.encode())


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError) as e:
        raise SecretError("segredo inválido ou chave trocada") from e
