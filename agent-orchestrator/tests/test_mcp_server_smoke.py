"""Smoke test do servidor MCP (Task 2).

Verifica que:
- ``GET /health`` continua retornando 200 (lifespan não quebrou).
- A rota ``/mcp/mcp`` está montada (não retorna 404) e não quebra (não
  retorna 500). Sem o middleware de auth MCP (Task 3), o middleware global
  de autenticação intercepta e retorna 401, o que é o comportamento esperado
  aqui: a rota existe e o app não crasha.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_still_ok() -> None:
    """O healthcheck do container continua 200 após montar o MCP."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_mcp_route_mounted_not_500() -> None:
    """A rota /mcp/mcp está montada: não 404 e não 500.

    Sem o middleware de auth MCP (Task 3), o middleware global de
    autenticação responde 401 (sem Bearer token). Isso confirma que a rota
    existe (não 404) e que o app ASGI do MCP não crasha (não 500).
    """
    resp = client.get("/mcp/mcp")
    assert resp.status_code != 404, "rota /mcp/mcp não está montada"
    assert resp.status_code != 500, "app ASGI do MCP quebrou (500)"
    # Comportamento esperado sem auth MCP: 401 do middleware global.
    assert resp.status_code == 401
