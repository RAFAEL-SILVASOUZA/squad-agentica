"""FastAPI application entrypoint.

Dono: infra-docker. Contrato §3:
- Expõe ``GET /health`` (container) e ``GET /api/health`` (via NGINX).
- Descoberta automática de routers: todo módulo em ``app/api/`` que exponha
  ``router = APIRouter(...)`` é incluído automaticamente. Nós paralelos só
  criam o próprio arquivo em ``app/api/<dominio>.py``; ninguém edita main.py.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.errors import register_exception_handlers

app = FastAPI(title="Agent Portal Orchestrator", version="0.1.0")

# CORS defensivo (na prática a mesma origem via NGINX; contrato §2).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Envelope de erro padrão (contrato §8).
register_exception_handlers(app)


@app.get("/health")
async def health() -> dict[str, str]:
    """Healthcheck do container (Docker)."""
    return {"status": "ok"}


@app.get("/api/health")
async def api_health() -> dict[str, str]:
    """Healthcheck da API (via NGINX, mantém o prefixo /api)."""
    return {"status": "ok"}


def _discover_routers() -> None:
    """Inclui automaticamente todo router em app/api/ (contrato §3)."""
    api_pkg = importlib.import_module("app.api")
    api_dir = Path(api_pkg.__file__).parent
    for module_info in pkgutil.iter_modules([str(api_dir)]):
        module = importlib.import_module(f"app.api.{module_info.name}")
        router = getattr(module, "router", None)
        if router is not None:
            app.include_router(router, prefix="/api")


_discover_routers()
