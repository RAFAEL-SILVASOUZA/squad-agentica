"""Teste da descoberta automática de routers (contrato §3).

Cria um módulo temporário em app/api/ com ``router = APIRouter()``, recarrega
o app, verifica que a rota aparece em /api/probe, e limpa.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient

API_DIR = Path(__file__).resolve().parent.parent / "app" / "api"
PROBE_MODULE = "app.api._probe_test"
PROBE_FILE = API_DIR / "_probe_test.py"

PROBE_SOURCE = (
    "from fastapi import APIRouter\n"
    "router = APIRouter()\n"
    "\n"
    "@router.get('/probe')\n"
    "async def probe() -> dict:\n"
    "    return {'probed': True}\n"
)


def _reload_app():
    import app.main as main

    importlib.reload(main)
    return main.app


def test_router_discovery(tmp_path: Path) -> None:
    # Garante estado limpo.
    app = _reload_app()
    assert not any(r.path == "/api/probe" for r in app.routes)

    # Cria o módulo de prova.
    PROBE_FILE.write_text(PROBE_SOURCE, encoding="utf-8")
    try:
        app = _reload_app()
        assert any(r.path == "/api/probe" for r in app.routes), "router de prova não foi descoberto"

        client = TestClient(app)
        # Route is discovered AND protected by global auth (contrato §5).
        resp = client.get("/api/probe")
        assert resp.status_code == 401, "new router should be protected by default"
    finally:
        # Limpa o módulo e o cache para não vazar para outros testes.
        PROBE_FILE.unlink(missing_ok=True)
        sys.modules.pop(PROBE_MODULE, None)
        _reload_app()
