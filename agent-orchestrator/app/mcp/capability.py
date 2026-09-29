"""Capacidade por run para a ponte MCP interna (revisão final I4).

O token compartilhado dos workers (``X-Worker-Token``) sozinho deixava
qualquer chamador com esse token pedir ferramentas MCP de QUALQUER dono, com
QUALQUER workspace como cwd. Agora o orchestrator emite, ao despachar um nó,
um HMAC sobre ``runId|ownerId|workspaceDir``; o worker só repassa esse valor
nas chamadas ``/internal/mcp`` e a ponte confere (``compare_digest``) que o
dono e o workspace pedidos são exatamente os do run despachado.
"""

from __future__ import annotations

import hashlib
import hmac

from app.core.config import settings


def _secret() -> bytes:
    if settings.mcp_capability_secret:
        return settings.mcp_capability_secret.encode()
    # Derivado (nunca igual) de um segredo que só o orchestrator conhece.
    base = settings.integrations_secret_key or settings.jwt_secret
    return hashlib.sha256(f"agent-portal/mcp-capability/{base}".encode()).digest()


def _message(run_id: str | None, owner_id: str | None, workspace_dir: str | None) -> bytes:
    return f"{run_id or ''}|{owner_id or ''}|{workspace_dir or ''}".encode()


def mint_mcp_capability(
    run_id: str | None, owner_id: str | None, workspace_dir: str | None
) -> str:
    message = _message(run_id, owner_id, workspace_dir)
    return hmac.new(_secret(), message, hashlib.sha256).hexdigest()


def verify_mcp_capability(
    capability: str | None, run_id: str | None, owner_id: str | None, workspace_dir: str | None
) -> bool:
    if not capability:
        return False
    expected = mint_mcp_capability(run_id, owner_id, workspace_dir)
    return hmac.compare_digest(capability.encode(), expected.encode())
