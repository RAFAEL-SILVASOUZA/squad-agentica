"""Spike worker: FastAPI mínimo com POST /execute que SIMULA um agente.

Sem LLM real, sem MinIO, sem auth. Resposta determinística derivada dos inputs,
com opções de falhar e de demorar (para testar retry/timeout do worker_client).

Contrato HTTP (contrato técnico §2.3):
  Request  POST /execute  { agentId, nodeId, inputs, timeout }
  Response 200 { status: "completed"|"failed", outputs, action, iterations, logs }

O worker é stateless e genérico: não sabe qual agente vai rodar até receber a request.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="spike-worker")


class ExecuteRequest(BaseModel):
    agentId: str
    nodeId: str
    inputs: dict[str, Any] = {}
    timeout: int = 60
    # opções de teste (não fazem parte do contrato real; só para o spike):
    fail: bool = False
    delay: float = 0.0


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/execute")
async def execute(req: ExecuteRequest) -> dict[str, Any]:
    """Simula a execução de um agente. Determinístico.

    Comportamento:
      - delay > 0: dorme `delay` segundos (simula agente demorado / timeout).
      - fail: devolve status="failed" com um erro estruturado (sem stack trace).
      - senão: devolve status="completed" com outputs derivados dos inputs.

    O output é determinístico: cada output port recebe um valor derivado do input
    correspondente (ou do agentId), com um marker verificável nos testes.
    """
    started = time.monotonic()

    if req.delay > 0:
        await asyncio.sleep(req.delay)

    if req.fail:
        return {
            "status": "failed",
            "outputs": {},
            "action": "follow",
            "iterations": 1,
            "logs": [f"[{req.agentId}] simulated failure (requested)"],
            "error": "simulated worker failure",
        }

    # Determinístico: outputs derivados dos inputs.
    # Convenção do spike: para cada input port, o output port homônimo recebe
    # "<agentId>:<input_value>". Se não há input, gera um output "result".
    outputs: dict[str, Any] = {}
    for port, value in req.inputs.items():
        outputs[port] = f"{req.agentId}:{value}"
    if not outputs:
        outputs["result"] = f"{req.agentId}:done"

    elapsed = time.monotonic() - started
    return {
        "status": "completed",
        "outputs": outputs,
        "action": "follow",
        "iterations": 1,
        "logs": [
            f"[{req.agentId}] executed in {elapsed:.3f}s",
            f"[{req.agentId}] inputs={req.inputs} outputs={outputs}",
        ],
    }
