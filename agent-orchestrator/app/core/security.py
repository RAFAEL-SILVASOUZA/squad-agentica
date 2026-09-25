"""Password hashing (bcrypt, cost 12) and JWT helpers.

Dono: infra-docker. Consumido pelo seed (db-seed) e pelo auth-backend.
"""

import bcrypt

# Custo 12 exigido pelo contrato §5.
_BCRYPT_ROUNDS = 12


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt (cost 12). Returns the hash as str."""
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a bcrypt hash. Never raises."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False
