"""Tests for the Rivvn stub (D9, contrato §10: fora do caminho crítico da V1).

Cobre: a fonte ``rivvn`` responde erro claro "não disponível" (501) quando
acionada. O gateway OAuth (authorize/callback/status/DELETE) é do nó
be-integrations; aqui só a lógica de negócio (stub) é testada.
"""

from __future__ import annotations

import pytest

from app.core.errors import AppError
from app.knowledge.rivvn import is_rivvn_available, rivvn_query


class TestRivvnStub:
    def test_rivvn_not_available(self):
        """Rivvn não está disponível na V1 (contrato §10)."""
        assert is_rivvn_available() is False

    def test_rivvn_query_raises_not_available(self):
        """Acionar a query do Rivvn levanta erro claro 501."""
        with pytest.raises(AppError) as exc:
            rivvn_query("some query", ["kb1"])
        assert exc.value.status_code == 501
        assert exc.value.code == "rivvn_not_available"
        msg = exc.value.error.lower()
        assert "não disponível" in msg or "not available" in msg
