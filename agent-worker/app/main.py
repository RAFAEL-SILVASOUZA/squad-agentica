"""Agent worker: FastAPI entrypoint.

Dono: rt-worker (FASE 6). Contrato (CONTRATO-TECNICO 2.3):
- ``GET /health``  -> 200 (healthcheck do container).
- ``POST /execute`` -> executa um agente por request.

O worker e stateless e generico: nao sabe qual agente vai rodar ate receber
a request. Baixa o .yml do agente do Garage, monta o snapshot, chama o
loader para derivar capacidades, executa o agente (LLM + tool calls) e
devolve output + action + logs.

Auth: header ``X-Worker-Token`` obrigatorio (segredo compartilhado).
Sem token ou token errado -> 401.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.worker import execute_agent
from app.workspace_guard import WORKSPACES_ROOT

# ---------------------------------------------------------------------------
# Logging estruturado (contrato 8: JSON no stdout, sem segredos)
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}',
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Agent Portal Worker", version="0.2.0")

# Token compartilhado (do ambiente).
WORKER_TOKEN = os.environ.get("WORKER_TOKEN", "change-me-in-prod")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ExecuteRequest(BaseModel):
    """Body de POST /execute (contrato 2.3)."""

    agentId: str = Field(..., description="UUID do agente")
    nodeId: str = Field(..., description="ID do no na pipeline")
    inputs: dict[str, Any] = Field(default_factory=dict, description="Dados de entrada")
    timeout: int = Field(default=60, ge=1, le=600, description="Timeout em segundos")
    workspaceDir: str | None = Field(
        default=None, description="Workspace do run (spec 14.1), confina as ferramentas"
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    """Healthcheck do container (Docker)."""
    return {"status": "ok"}


@app.post("/execute")
async def execute(request: Request) -> JSONResponse:
    """Executa um agente (contrato 2.3).

    - Auth: header ``X-Worker-Token`` (401 se ausente/errado).
    - Body: ``{agentId, nodeId, inputs, timeout}``.
    - Response 200: ``{status, outputs, action, iterations, logs}``.
    - Response 404: ``{error: "agent_not_found", code: "agent_not_found"}``.
    - Erros: resposta estruturada (nunca stack trace cru).
    """
    # 1. Auth.
    token = request.headers.get("X-Worker-Token", "")
    if token != WORKER_TOKEN:
        return JSONResponse(
            status_code=401,
            content={"error": "unauthorized", "code": "worker_token_invalid"},
        )

    # 2. Parse body.
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid request body", "code": "invalid_body"},
        )

    try:
        req = ExecuteRequest(**body)
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={
                "error": "validation error",
                "code": "invalid_body",
                "details": {"errors": [str(e)]},
            },
        )

    # 3. Valida workspaceDir (precisa estar dentro de WORKSPACES_DIR).
    if req.workspaceDir is not None:
        resolved_workspace = Path(req.workspaceDir).resolve()
        workspaces_root = WORKSPACES_ROOT.resolve()
        is_inside = (
            resolved_workspace == workspaces_root
            or workspaces_root in resolved_workspace.parents
        )
        if not is_inside:
            return JSONResponse(
                status_code=400,
                content={"error": "invalid workspace", "code": "invalid_workspace"},
            )

    # 4. Executa o agente.
    logger.info(
        "Execute request: agent_id=%s node_id=%s timeout=%d",
        req.agentId,
        req.nodeId,
        req.timeout,
    )

    result = await execute_agent(
        agent_id=req.agentId,
        node_id=req.nodeId,
        inputs=req.inputs,
        timeout=req.timeout,
        workspace_dir=req.workspaceDir,
    )

    # 5. Monta a resposta.
    if result.status == "failed" and result.error and "not found" in result.error.lower():
        return JSONResponse(
            status_code=404,
            content={"error": "agent_not_found", "code": "agent_not_found"},
        )

    response: dict[str, Any] = {
        "status": result.status,
        "outputs": result.outputs,
        "action": result.action,
        "iterations": result.iterations,
        "logs": result.logs,
    }
    if result.error:
        response["error"] = result.error

    return JSONResponse(status_code=200, content=response)
