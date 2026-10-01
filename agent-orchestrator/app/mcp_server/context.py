"""Contexto de usuário do servidor MCP.

O middleware de autenticação MCP (Task 3) resolve o usuário a partir do
token e popula ``current_user`` antes de cada chamada de ferramenta. As
ferramentas leem o usuário via :func:`get_current_mcp_user`.

Usamos ``contextvars`` porque o MCP roda em um app ASGI separado (montado
em ``/mcp``) e o contexto precisa atravessar a fronteira entre o middleware
e a execução da ferramenta sem passar por parâmetros explícitos.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    # Import apenas para type-checking: evita import circular em runtime
    # (models.py não importa nada daqui, mas mantemos a dependência solta).
    from app.db.models import User

# Usuário autenticado da chamada MCP atual (None fora de uma chamada).
current_user: ContextVar[Optional["User"]] = ContextVar("current_user", default=None)


def get_current_mcp_user() -> Optional["User"]:
    """Retorna o usuário autenticado da chamada MCP atual (ou ``None``)."""
    return current_user.get()
