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
    ownerId: str | None = None
    mcpServers: list[dict[str, Any]] | None = None
    nodeId: str = Field(..., description="ID do no na pipeline")
    inputs: dict[str, Any] = Field(default_factory=dict, description="Dados de entrada")
    timeout: int = Field(default=60, ge=1, le=600, description="Timeout em segundos")
    workspaceDir: str | None = Field(
        default=None, description="Workspace do run (spec 14.1), confina as ferramentas"
    )
    # Capacidade MCP do run (emitida pelo orchestrator; só repassada à ponte).
    runId: str | None = None
    mcpCapability: str | None = None
    # Conexão de LLM resolvida pelo orchestrator (adendo 8): {kind, baseUrl,
    # apiKey, model}. Vive só no body; nunca é logada nem persistida.
    llm: dict[str, Any] | None = None


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

    # 3. Valida workspaceDir: precisa ser descendente ESTRITO de WORKSPACES_DIR
    #    (a própria raiz daria ao agente acesso aos workspaces de outros runs).
    workspace_dir: str | None = None
    if req.workspaceDir is not None:
        try:
            resolved_workspace = Path(req.workspaceDir).resolve()
        except (ValueError, TypeError, OSError):
            resolved_workspace = None
        workspaces_root = WORKSPACES_ROOT.resolve()
        if resolved_workspace is None or workspaces_root not in resolved_workspace.parents:
            return JSONResponse(
                status_code=400,
                content={"error": "invalid workspace", "code": "invalid_workspace"},
            )
        # O worker nunca cria o workspace de um run: se ele não existe (run
        # expirado/removido), é erro — recriar vazio "perderia" o trabalho.
        if not resolved_workspace.is_dir():
            return JSONResponse(
                status_code=400,
                content={
                    "error": "invalid workspace",
                    "code": "invalid_workspace",
                    "details": {
                        "message": (
                            "O workspace deste run não existe mais (expirou ou foi removido)."
                        )
                    },
                },
            )
        # Usa o caminho resolvido (sem ``..``/symlinks) daqui em diante.
        workspace_dir = str(resolved_workspace)

    # 4. Executa o agente.
    logger.info(
        "Execute request: agent_id=%s node_id=%s timeout=%d",
        req.agentId,
        req.nodeId,
        req.timeout,
    )

    execute_options = {}
    if req.mcpServers is not None:
        execute_options["mcp_servers"] = req.mcpServers
    if req.mcpCapability:
        execute_options["mcp_capability"] = req.mcpCapability
        execute_options["run_id"] = req.runId
    result = await execute_agent(
        agent_id=req.agentId,
        node_id=req.nodeId,
        inputs=req.inputs,
        timeout=req.timeout,
        workspace_dir=workspace_dir,
        owner_id=req.ownerId,
        llm_block=req.llm,
        **execute_options,
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
