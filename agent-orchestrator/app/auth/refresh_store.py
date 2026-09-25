"""In-memory refresh token rotation store.

Dono: auth-backend (FASE 3). Contrato §5:
- Rotação de refresh: refresh token usado é invalidado após uso.
- V1 single-user: in-memory dict. V2: Redis.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class _RefreshEntry:
    """Tracks a refresh token's lifecycle."""

    jti: str
    sub: str
    created_at: float = field(default_factory=time.time)
    used: bool = False
    replaced_by: str | None = None  # jti of the new token that replaced this one


class RefreshTokenStore:
    """In-memory store for refresh token rotation.

    Thread-safe. Tracks which refresh tokens have been used so that
    reusing an old token is detected (rotation invalidation).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: dict[str, _RefreshEntry] = {}  # jti -> entry

    def issue(self, jti: str, sub: str) -> None:
        """Register a newly issued refresh token."""
        with self._lock:
            self._tokens[jti] = _RefreshEntry(jti=jti, sub=sub)

    def rotate(self, old_jti: str, new_jti: str, sub: str) -> bool:
        """Mark old token as used and register the new one.

        Returns True if rotation succeeded (old token was valid and unused).
        Returns False if the old token was already used (replay detected).
        """
        with self._lock:
            entry = self._tokens.get(old_jti)
            if entry is None:
                return False
            if entry.used:
                # Replay detected: old token was already rotated.
                return False
            entry.used = True
            entry.replaced_by = new_jti
            self._tokens[new_jti] = _RefreshEntry(jti=new_jti, sub=sub)
            return True

    def is_valid(self, jti: str) -> bool:
        """Check if a refresh token jti is valid (exists and not used)."""
        with self._lock:
            entry = self._tokens.get(jti)
            if entry is None:
                return False
            return not entry.used

    def cleanup(self, max_age_seconds: float = 7 * 24 * 3600) -> None:
        """Remove entries older than max_age (7 days default)."""
        with self._lock:
            now = time.time()
            expired = [
                jti
                for jti, entry in self._tokens.items()
                if now - entry.created_at > max_age_seconds
            ]
            for jti in expired:
                del self._tokens[jti]


# Module-level singleton (V1 single-user, in-memory).
refresh_store = RefreshTokenStore()
