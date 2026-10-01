"""Instância do servidor MCP (FastMCP) e seu lifespan.

``mcp`` é a instância ``FastMCP`` (v1 API) configurada em modo
``stateless_http``: cada request HTTP é tratado de forma independente, sem
estado de sessão persistente em memória. Isso simplifica a escala horizontal
e a autenticação por request (o token é validado a cada chamada).

``mcp_lifespan`` entra no ``session_manager.run()`` do FastMCP para que o
app ASGI interno (``mcp.streamable_http_app()``) esteja pronto para atender.
O ``main.py`` o compõe com o lifespan principal via ``AsyncExitStack``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

# Instância única do servidor MCP. ``stateless_http=True``: sem estado de
# sessão em memória (adequado para auth por request e escala horizontal).
#
# ``transport_security`` desabilita a proteção DNS rebinding do FastMCP:
# o servidor fica atrás do nginx (reverse proxy) e cada request já exige um
# token Bearer válido (middleware de auth), então a validação de Host/Origin
# do transporte é redundante e quebraria atrás do proxy (o header ``Host``
# chega sem porta, ex.: ``localhost``, e não casa com o padrão ``localhost:*``
# que o FastMCP ativa por padrão, retornando 421).
mcp = FastMCP(
    "AgentPortal",
    stateless_http=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


@asynccontextmanager
async def mcp_lifespan() -> AsyncIterator[None]:
    """Lifespan do servidor MCP: mantém o session manager ativo.

    Entra em ``mcp.session_manager.run()`` no startup e o encerra no
    shutdown. O ``main.py`` o compõe com o lifespan principal para que o
    app ASGI do MCP (montado em ``/mcp``) esteja pronto para atender.
    """
    async with mcp.session_manager.run():
        yield


def mcp_auth_app():
    """Retorna o app ASGI do MCP com o middleware de autenticação aplicado.

    O ``main.py`` monta este app em ``/mcp``. O middleware valida o token
    Bearer (JWT typ="mcp") antes de encaminhar ao streamable HTTP do FastMCP.
    """
    from app.mcp_server.auth import MCPAuthMiddleware

    return MCPAuthMiddleware(mcp.streamable_http_app())


# Importa o pacote de tools para registrar os handlers no ``mcp``.
# Cada módulo em ``tools/`` usa ``@mcp.tool()`` no import, então basta
# importar o pacote para as tools ficarem disponíveis no servidor.
import app.mcp_server.tools  # noqa: E402,F401
