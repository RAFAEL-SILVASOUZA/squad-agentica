"""Ferramentas MCP do Agent Portal.

Este pacote agrupa todos os módulos de ferramentas MCP. Cada módulo registra
suas ferramentas no servidor FastMCP via ``@mcp.tool()``. O import dos
módulos aqui garante que as ferramentas sejam registradas quando o pacote
é carregado.

Novos módulos de ferramentas devem ser importados aqui (com try/except
ImportError para permitir desenvolvimento incremental).
"""

from __future__ import annotations


class ToolError(Exception):
    """Erro de tool MCP com mensagem amigável para o cliente."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# Import dos módulos de ferramentas (registra as tools no servidor MCP).
# try/except ImportError permite que módulos futuros não quebrem o pacote
# enquanto ainda não existem.
from app.mcp_server.tools import agents  # noqa: F401

try:
    from app.mcp_server.tools import pipelines  # noqa: F401
except ImportError:
    pass

try:
    from app.mcp_server.tools import runs  # noqa: F401
except ImportError:
    pass

try:
    from app.mcp_server.tools import mcp_servers  # noqa: F401
except ImportError:
    pass

try:
    from app.mcp_server.tools import integrations  # noqa: F401
except ImportError:
    pass

try:
    from app.mcp_server.tools import knowledge  # noqa: F401
except ImportError:
    pass

try:
    from app.mcp_server.tools import skills  # noqa: F401
except ImportError:
    pass

try:
    from app.mcp_server.tools import tools  # noqa: F401
except ImportError:
    pass

try:
    from app.mcp_server.tools import workspaces  # noqa: F401
except ImportError:
    pass

try:
    from app.mcp_server.tools import approvals  # noqa: F401
except ImportError:
    pass
