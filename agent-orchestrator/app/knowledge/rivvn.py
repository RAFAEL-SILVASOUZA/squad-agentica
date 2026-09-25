"""Rivvn: fonte externa de Knowledge Base (stub, fora do caminho crítico da V1).

Dono: be-knowledge (FASE 4). Contrato §10: Rivvn é **fora do caminho crítico
da V1**. O tipo de fonte ``source="rivvn"`` é mantido no model, mas a
integração (OAuth + SDK) não é implementada.

Comportamento:
- ``is_rivvn_available()`` -> ``False`` (sempre, na V1).
- ``rivvn_query(...)`` -> levanta ``AppError(501, "rivvn_not_available")`` com
  mensagem clara "não disponível na V1".

O gateway OAuth (``/api/integrations/rivvn/authorize|callback|status|DELETE``)
é do nó **be-integrations** (contrato §9, FASE 4). Este módulo entrega só a
lógica de negócio (stub) que o be-integrations consome.

V2: implementar ``oauth.py`` (authorization code flow) e ``client.py``
(wrapper do SDK do Rivvn), gateados por ``contractStatus === "active"``.
"""

from __future__ import annotations

from typing import Any

from app.core.errors import AppError


def is_rivvn_available() -> bool:
    """Rivvn não está disponível na V1 (contrato §10). Sempre ``False``."""
    return False


def rivvn_query(query: str, knowledge_base_ids: list[str], **_kwargs: Any) -> None:
    """Query do Rivvn: fora do caminho crítico da V1.

    Raises:
        AppError(501, "rivvn_not_available"): sempre, na V1.
    """
    raise AppError(
        501,
        "not available",
        "rivvn_not_available",
        {
            "message": (
                "Rivvn não está disponível na V1 (requer contrato comercial ativo). "
                "Use uma Knowledge Base com source='upload'."
            )
        },
    )
