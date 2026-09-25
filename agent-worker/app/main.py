"""Agent worker — FastAPI entrypoint (scaffold, dono: infra-docker).

Contrato §2.3: o worker é stateless e genérico. Ele expõe:
- ``GET /health``  -> 200 (healthcheck do container).
- ``POST /execute`` -> stub 501 no scaffold; o nó ``rt-worker`` (FASE 6)
  implementa a execução real (baixa .yml/.md do MinIO, roda o agente, devolve
  output + action + logs).

O worker **não** tem porta publicada nem rota na :80: o orchestrator o chama
pelo server block interno do NGINX (:8081) com o header ``X-Worker-Token``.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Agent Portal Worker", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    """Healthcheck do container (Docker)."""
    return {"status": "ok"}


@app.post("/execute")
async def execute(request: Request) -> JSONResponse:
    """Stub de execução (501).

    O nó ``rt-worker`` substitui este handler pela implementação real.
    Contrato §2.3: body ``{agentId, nodeId, inputs, timeout}``; response 200
    ``{status, outputs, action, iterations, logs}``.
    """
    return JSONResponse(
        status_code=501,
        content={
            "error": "not implemented",
            "code": "execute_not_implemented",
        },
    )
