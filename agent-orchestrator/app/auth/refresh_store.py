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
    used_at: float | None = None
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

        O chamador já validou assinatura, tipo e expiração do token. Regras:
        - jti desconhecido: o store é em memória e se perde a cada restart do
          orchestrator; o token é legítimo, então é aceito e registrado (sem
          isto todo restart derrubava as sessões em até 15 min). Efeito
          colateral aceito: a detecção de reuso não sobrevive a um restart.
        - jti já usado: replay; recusa (contrato §5, rotação estrita). As
          renovações concorrentes do NextAuth são deduplicadas no portal.
        """
        now = time.time()
        with self._lock:
            entry = self._tokens.get(old_jti)
            if entry is None:
                entry = _RefreshEntry(jti=old_jti, sub=sub)
                self._tokens[old_jti] = entry
            elif entry.used:
                # Replay detected: old token was already rotated.
                return False
            entry.used = True
            entry.used_at = now
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
