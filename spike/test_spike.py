"""Testes do spike LangGraph.

Cobrem: aprovar, rejeitar (loop-back), worker fora do ar (nó failed, grafo não aborta),
limite de iterações, e resume após reiniciar o processo.

Rode com o Postgres do spike de pé:
    docker compose -p spike -f spike/docker-compose.yml up -d
    .venv/Scripts/python.exe -m pytest test_spike.py -v

O worker é substituído por um stub (monkeypatch de worker_execute) para determinismo.
O Postgres real (spike) é usado para o checkpointer (PostgresSaver).
"""

from __future__ import annotations

import os
from typing import Any

import pytest

pytestmark = pytest.mark.asyncio

# URL do Postgres isolado do spike (docker-compose -p spike).
os.environ.setdefault("SPIKE_DATABASE_URL", "postgresql://spike:spike@localhost:15433/spike")
os.environ.setdefault("SPIKE_WORKER_URL", "http://localhost:9100")

from main import (  # noqa: E402
    PostgresSaver,
    State,
    PipelineJSON,
    compile_and_resume,
    compile_pipeline,
    run_pipeline,
    worker_execute,
)
from psycopg import connect  # noqa: E402
from langgraph.types import Command  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures do Postgres real (spike).
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def pg():
    conn = connect(os.environ["SPIKE_DATABASE_URL"], autocommit=True)
    saver = PostgresSaver(conn)
    saver.setup()
    yield saver
    conn.close()


# ---------------------------------------------------------------------------
# Worker stub: substitui worker_execute por respostas determinísticas.
# ---------------------------------------------------------------------------
class StubWorker:
    """Simula o worker: determinístico, com opções de falhar/demorar."""

    def __init__(self, fail: bool = False, delay: float = 0.0):
        self.fail = fail
        self.delay = delay
        self.calls = []

    async def __call__(self, agent_id, inputs, **kwargs):
        self.calls.append((agent_id, inputs))
        if self.fail:
            return _resp("failed", {}, "follow", error="simulated worker failure")
        outputs = {k: f"{agent_id}:{v}" for k, v in inputs.items()}
        if not outputs:
            outputs["result"] = f"{agent_id}:done"
        return _resp("completed", outputs, "follow")


def _resp(status, outputs, action, error=None):
    from main import WorkerResponse

    return WorkerResponse(
        status=status,
        outputs=outputs,
        action=action,
        iterations=1,
        logs=[f"[{status}] simulated"],
        error=error,
    )


@pytest.fixture
def stub_worker(monkeypatch):
    stub = StubWorker()
    monkeypatch.setattr("main.worker_execute", stub)
    return stub


# ---------------------------------------------------------------------------
# JSON de pipeline reutilizável: A -> [aprovação] -> B.
# ---------------------------------------------------------------------------
def _pipeline_json(**overrides):
    base = {
        "entry_node_id": "agent_a",
        "nodes": {
            "agent_a": {"agent_id": "agent-a", "max_iterations": 10},
            "agent_b": {"agent_id": "agent-b", "max_iterations": 10},
        },
        "edges": {
            "e1": {
                "source": "agent_a",
                "target": "agent_b",
                "requires_approval": True,
                "message": "Aprovar saída do agente A?",
            },
        },
    }
    base.update(overrides)
    return base


def _config(thread_id=None, run_id="run-1"):
    """Gera um config com thread_id único por padrão (evita colisão com checkpoints
    persistidos em execuções anteriores)."""
    if thread_id is None:
        import uuid
        thread_id = f"t-{uuid.uuid4().hex[:8]}"
    return {"configurable": {"thread_id": thread_id, "run_id": run_id}}


def _initial_state():
    return {
        "data": {"agent_a": {"prompt": "hello"}, "agent_b": {}},
        "iterations": {},
        "status": {},
        "actions": {},
        "max_iter_exceeded": False,
        "pipeline_status": "running",
    }


# ---------------------------------------------------------------------------
# Testes.
# ---------------------------------------------------------------------------
async def test_compile_pipeline_builds_graph():
    """ADR-004: JSON -> StateGraph com nós de aprovação gerados."""
    graph = compile_pipeline(PipelineJSON(**_pipeline_json())).compile()
    # Nós: agent_a, agent_b, approval_e1.
    assert "agent_a" in graph.nodes
    assert "agent_b" in graph.nodes
    assert any("approval" in n for n in graph.nodes)


async def test_approve_completes_pipeline(stub_worker, pg):
    """ADR-006: aprovar -> Command(goto=target) -> agente B roda -> pipeline completa."""
    pipeline = _pipeline_json()
    config = _config()
    initial = _initial_state()

    # Primeira execução: pausa no nó de aprovação (interrupt).
    result = await run_pipeline(pipeline, pg, config, initial)
    assert result["interrupted"] is True

    # Retomada com resume="approved": o nó de aprovação retorna Command(goto=agent_b).
    final = await compile_and_resume(
        pipeline, pg, config, resume_value="approved"
    )
    # agente B executou (output namespaceado por nodeId, ADR-003).
    assert final["data"]["agent_b"]["result"] == "agent-b:done"
    assert final["pipeline_status"] == "running"
    # agente A rodou uma vez.
    assert final["iterations"]["agent_a"] == 1


async def test_reject_loops_back(stub_worker, pg):
    """ADR-006: rejeitar -> Command(goto=source) -> loop-back pro agente A."""
    pipeline = _pipeline_json()
    config = _config()
    initial = _initial_state()

    # Pausa na aprovação.
    await run_pipeline(pipeline, pg, config, initial)

    # Rejeita: o nó de aprovação retorna Command(goto=agent_a) (loop-back).
    # Como o node function do agente A roda de novo, o grafo pausa novamente.
    final = await compile_and_resume(pipeline, pg, config, resume_value="rejected")
    # Loop-back re-executa agent_a; iterations de agent_a >= 2.
    assert final["iterations"]["agent_a"] >= 2


async def test_worker_down_node_failed_graph_survives(pg):
    """ADR-001: worker fora do ar -> nó failed, grafo NÃO aborta."""
    # Worker que sempre falha (simula worker fora do ar).
    import main

    async def failing_worker(agent_id, inputs, **kwargs):
        return _resp("failed", {}, "follow", error="worker unreachable")

    main.worker_execute = failing_worker

    pipeline = _pipeline_json()
    config = _config()
    initial = _initial_state()

    # O grafo executa mesmo com worker falhando: nó A fica failed, pipeline failed,
    # mas NÃO levanta exceção. A aresta A->aprovação é incondicional, então o grafo
    # segue para o nó de aprovação (que pausa). O ponto chave: NÃO aborta com exceção.
    result = await run_pipeline(pipeline, pg, config, initial)
    # O nó A ficou failed (worker falhou), mas o grafo não abortou: seguiu para a
    # aprovação (interrupt). Isso prova que a falha do worker não propaga exceção.
    assert result["state"]["status"]["agent_a"] == "failed"
    assert result["state"]["pipeline_status"] == "failed"
    # O grafo seguiu para o nó de aprovação (não abortou).
    assert result["interrupted"] is True


async def test_max_iterations_cuts_loop(stub_worker, pg):
    """ADR-005/007: maxIterations checado no início; loop cortado para END."""
    # agent_a com max_iterations=2 e loop-back por rejeição.
    pipeline = _pipeline_json(
        nodes={
            "agent_a": {"agent_id": "agent-a", "max_iterations": 2},
            "agent_b": {"agent_id": "agent-b", "max_iterations": 10},
        },
        edges={
            "e1": {
                "source": "agent_a",
                "target": "agent_b",
                "requires_approval": True,
                "reject_target": "agent_a",  # loop-back explícito
                "message": "Aprovar?",
            }
        },
    )
    config = _config()
    initial = _initial_state()

    # Pausa na aprovação; rejeita -> loop-back. Repete até max_iterations.
    await run_pipeline(pipeline, pg, config, initial)
    final = None
    for _ in range(5):
        final = await compile_and_resume(pipeline, pg, config, resume_value="rejected")
        if final["pipeline_status"] == "failed":
            break

    # Após max_iterations, o nó A não roda mais (guarda no início, ADR-007) e a
    # pipeline vai para failed. iterations de agent_a == 2 (executou 2 vezes).
    assert final["iterations"]["agent_a"] == 2
    assert final["max_iter_exceeded"] is True
    assert final["pipeline_status"] == "failed"


async def test_resume_after_process_restart(stub_worker, pg):
    """ADR-004: resume após reiniciar o processo (novo grafo compilado).

    Simula um novo processo: novo saver, novo grafo compilado do JSON e retoma.
    O checkpoint sobrevive (PostgresSaver por thread_id).
    """
    pipeline = _pipeline_json()
    config = _config()
    initial = _initial_state()

    # Processo 1: executa e pausa.
    await run_pipeline(pipeline, pg, config, initial)

    # "Reinicia o processo": novo saver, novo grafo compilado (ADR-004).
    from psycopg import connect

    conn = connect(os.environ["SPIKE_DATABASE_URL"], autocommit=True)
    saver2 = PostgresSaver(conn)
    saver2.setup()

    # Retoma do checkpoint salvo (mesmo thread_id).
    final = await compile_and_resume(pipeline, saver2, config, resume_value="approved")
    assert final["data"]["agent_b"]["result"] == "agent-b:done"
    conn.close()


async def test_streaming_detects_interrupt(stub_worker, pg):
    """Streaming detecta interrupção via __interrupt__ no stream (updates mode)."""
    pipeline = _pipeline_json()
    config = _config()
    initial = _initial_state()

    events = []

    def on_event(ev):
        events.append(ev)

    result = await run_pipeline(pipeline, pg, config, initial, on_event=on_event)
    assert result["interrupted"] is True
    # O stream gerou um evento de interrupção.
    assert any(e["type"] == "interrupted" for e in events)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
