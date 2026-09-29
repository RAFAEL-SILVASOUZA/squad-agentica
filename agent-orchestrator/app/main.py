"""FastAPI application entrypoint.

Dono: infra-docker. Contrato §3:
- Expõe ``GET /health`` (container) e ``GET /api/health`` (via NGINX).
- Descoberta automática de routers: todo módulo em ``app/api/`` que exponha
  ``router = APIRouter(...)`` é incluído automaticamente. Nós paralelos só
  criam o próprio arquivo em ``app/api/<dominio>.py``; ninguém edita main.py.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import logging
import pkgutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.app_setup import apply_global_auth
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.log_redaction import install_log_redaction

logger = logging.getLogger(__name__)
# F16: o JWT do WebSocket vai na query string e o uvicorn a registra.
install_log_redaction()

# Task 8: limpeza periódica de workspaces expirados (retenção).
_PURGE_INTERVAL_SECONDS = 24 * 60 * 60


async def _run_workspace_purge() -> int:
    """Uma rodada de limpeza (``WorkspaceManager.purge_older_than``).

    É bloqueante (I/O de disco: ``shutil.rmtree`` por workspace), por isso
    roda em thread separada (``asyncio.to_thread``) para não travar o loop de
    eventos do orchestrator enquanto outros requests estão em andamento.
    """
    from sqlalchemy import select

    from app.db.models import PipelineRun
    from app.db.session import async_session_factory
    from app.runtime.workspace import WorkspaceManager

    # Revisão final I2: runs em andamento (running/paused) nunca são
    # purgados, por mais antigo que seja o último arquivo do workspace.
    async with async_session_factory() as session:
        active = {
            str(r) for r in (await session.execute(
                select(PipelineRun.id).where(PipelineRun.status.in_(["running", "paused"]))
            )).scalars().all()
        }
    removed = await asyncio.to_thread(
        WorkspaceManager().purge_older_than, settings.workspace_retention_days, active
    )
    logger.info("workspace_purge: %d workspace(s) removido(s)", removed)
    return removed


async def _purge_loop() -> None:
    """Roda a limpeza no startup e depois a cada 24h, até ser cancelada."""
    try:
        while True:
            await _run_workspace_purge()
            await asyncio.sleep(_PURGE_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        pass


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown (F2 + F6).

    F2: o checkpointer é inicializado no STARTUP (antes de qualquer request),
    não sob demanda no primeiro execute. Em banco novo, ``saver.setup()`` roda
    ``CREATE INDEX CONCURRENTLY``, que espera TODAS as transações abertas —
    inclusive a do próprio request que pediu o setup (deadlock: o primeiro
    execute nunca respondia). Fora do request, não há transação aberta e o
    setup completa.

    F6: o hook de aprovação do executor é registrado aqui (ADR-009). Sem
    isso, o interrupt era detectado mas a ApprovalRequest nunca era
    persistida nem notificada (``GET /api/approvals`` sempre vazio).
    """
    from app.api.pipeline_runs import get_executor
    from app.approvals.service import build_approval_hook
    from app.db.session import async_session_factory
    from app.runtime.executor import register_approval_hook

    register_approval_hook(build_approval_hook(async_session_factory))
    await get_executor()
    logger.info("startup: checkpointer pronto e hook de aprovação registrado")
    purge_task = asyncio.create_task(_purge_loop(), name="workspace-purge-loop")
    try:
        yield
    finally:
        from app.api.pipeline_runs import shutdown_executor

        purge_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await purge_task
        await shutdown_executor()


app = FastAPI(
    title="Agent Portal Orchestrator",
    version="0.1.0",
    lifespan=_lifespan,
)

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

# Proteção global opt-out (contrato §5): toda rota exige usuário exceto PUBLIC_PATHS.
apply_global_auth(app)


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
            app.include_router(router, prefix="" if module_info.name == "internal_mcp" else "/api")


_discover_routers()
