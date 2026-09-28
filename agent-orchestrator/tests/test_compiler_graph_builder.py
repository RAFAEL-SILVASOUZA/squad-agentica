"""Testes do pipeline compiler (graph_builder.py + state.py).

Cobrem:
  - Linear A->B->C
  - Fan-out (A -> B e A -> C em paralelo)
  - Loop com condição e maxIterations
  - Data edge sem flow edge (regra 7: injeta flow incondicional)
  - Aprovação com aprovar e rejeitar (MemorySaver)
  - Worker fake falhando (grafo não aborta)
  - Determinismo (compilar duas vezes, mesma topologia)

Rode com:
    docker compose -p squad-agentica run --rm --no-deps \
        --entrypoint pytest orchestrator tests/test_compiler_graph_builder.py -v
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.compiler.graph_builder import (
    AgentSnapshot,
    DataMapping,
    EdgeCondition,
    Pipeline,
    PipelineEdge,
    PipelineNode,
    PortDef,
    WorkerResponse,
    compile_pipeline,
    pipeline_from_dict,
)
from app.compiler.state import initial_state

# ---------------------------------------------------------------------------
# Fake WorkerClient (ADR-001: nunca levanta exceção)
# ---------------------------------------------------------------------------


class FakeWorker:
    """Worker fake determinístico para testes.

    Simula o worker: retorna respostas pré-definidas por agent_id.
    Nunca levanta exceção (ADR-001).
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses: dict[str, WorkerResponse] = {}
        self._default_action: str = "follow"
        self._fail: bool = False

    def set_response(self, agent_id: str, resp: WorkerResponse) -> None:
        self._responses[agent_id] = resp

    def set_default_action(self, action: str) -> None:
        self._default_action = action

    def set_fail(self, fail: bool) -> None:
        self._fail = fail

    async def execute(
        self,
        agent_id: str,
        node_id: str,
        inputs: dict[str, Any],
        *,
        timeout: int = 60,
    ) -> WorkerResponse:
        self.calls.append({"agent_id": agent_id, "node_id": node_id, "inputs": inputs})
        if self._fail:
            return WorkerResponse(
                status="failed",
                outputs={},
                action="follow",
                iterations=0,
                logs=[f"[{node_id}] simulated failure"],
                error="simulated worker failure",
            )
        if agent_id in self._responses:
            return self._responses[agent_id]
        # Default: completed, outputs = inputs transformados, action = default.
        outputs = {k: f"{agent_id}:{v}" for k, v in inputs.items()}
        if not outputs:
            outputs["result"] = f"{agent_id}:done"
        return WorkerResponse(
            status="completed",
            outputs=outputs,
            action=self._default_action,
            iterations=1,
            logs=[f"[{node_id}] completed"],
        )


@pytest.fixture
def fake_worker() -> FakeWorker:
    return FakeWorker()


@pytest.fixture
def checkpointer() -> MemorySaver:
    return MemorySaver()


# ---------------------------------------------------------------------------
# Helpers para construir pipelines de teste
# ---------------------------------------------------------------------------


def _make_node(
    node_id: str,
    agent_id: str,
    *,
    max_iterations: int = 10,
    inputs: list[PortDef] | None = None,
    outputs: list[PortDef] | None = None,
    actions: list[str] | None = None,
) -> PipelineNode:
    return PipelineNode(
        id=node_id,
        agent_id=agent_id,
        agent_snapshot=AgentSnapshot(
            agent_id=agent_id,
            name=agent_id,
            inputs=inputs or [],
            outputs=outputs or [],
            actions=actions or ["follow"],
            max_iterations=max_iterations,
            timeout=30,
        ),
    )


def _make_edge(
    edge_id: str,
    source: str,
    target: str,
    *,
    type: str = "flow",
    condition: EdgeCondition | None = None,
    requires_approval: bool = False,
    data_mapping: DataMapping | None = None,
    reject_target: str | None = None,
    approval_message: str | None = None,
    approval_channel: str | None = None,
) -> PipelineEdge:
    return PipelineEdge(
        id=edge_id,
        type=type,
        source=source,
        target=target,
        condition=condition,
        requires_approval=requires_approval,
        data_mapping=data_mapping,
        reject_target=reject_target,
        approval_message=approval_message,
        approval_channel=approval_channel,
    )


def _config(thread_id: str | None = None) -> dict[str, Any]:
    if thread_id is None:
        thread_id = f"t-{uuid.uuid4().hex[:8]}"
    return {"configurable": {"thread_id": thread_id, "run_id": "run-test"}}


# ---------------------------------------------------------------------------
# Teste 1: Linear A -> B -> C
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_linear_a_b_c(fake_worker: FakeWorker, checkpointer: MemorySaver):
    """Pipeline linear A -> B -> C: todos executam em sequência."""
    pipeline = Pipeline(
        id="p1",
        name="linear",
        entry_node_id="A",
        nodes=[
            _make_node("A", "agent-a"),
            _make_node("B", "agent-b"),
            _make_node("C", "agent-c"),
        ],
        edges=[
            _make_edge("e1", "A", "B"),
            _make_edge("e2", "B", "C"),
        ],
    )

    graph = compile_pipeline(pipeline, worker_client=fake_worker, checkpointer=checkpointer)
    config = _config()
    state = initial_state()

    result = await graph.ainvoke(state, config=config)

    # Todos os três nós executaram.
    assert result["status"]["A"] == "completed"
    assert result["status"]["B"] == "completed"
    assert result["status"]["C"] == "completed"
    assert result["iterations"]["A"] == 1
    assert result["iterations"]["B"] == 1
    assert result["iterations"]["C"] == 1
    assert result["pipeline_status"] == "running"
    # Worker foi chamado 3 vezes.
    assert len(fake_worker.calls) == 3


# ---------------------------------------------------------------------------
# Teste 2: Fan-out (A -> B e A -> C em paralelo)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fan_out(fake_worker: FakeWorker, checkpointer: MemorySaver):
    """Fan-out: A tem duas flow edges incondicionais (B e C). Ambos executam."""
    pipeline = Pipeline(
        id="p2",
        name="fanout",
        entry_node_id="A",
        nodes=[
            _make_node("A", "agent-a"),
            _make_node("B", "agent-b"),
            _make_node("C", "agent-c"),
        ],
        edges=[
            _make_edge("e1", "A", "B"),
            _make_edge("e2", "A", "C"),
        ],
    )

    graph = compile_pipeline(pipeline, worker_client=fake_worker, checkpointer=checkpointer)
    config = _config()
    state = initial_state()

    result = await graph.ainvoke(state, config=config)

    # A executou, B e C executaram (fan-out).
    assert result["status"]["A"] == "completed"
    assert result["status"]["B"] == "completed"
    assert result["status"]["C"] == "completed"
    assert result["iterations"]["A"] == 1
    assert result["iterations"]["B"] == 1
    assert result["iterations"]["C"] == 1


# ---------------------------------------------------------------------------
# Teste 3: Loop com condição e maxIterations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loop_with_condition_and_max_iterations(
    fake_worker: FakeWorker, checkpointer: MemorySaver
):
    """Loop A -> B -> A com condição (return) e maxIterations cortando o loop."""
    # A produz "follow" ou "return". B sempre retorna "return" (loop-back).
    # A tem max_iterations=3: após 3 execuções, o loop é cortado.
    pipeline = Pipeline(
        id="p3",
        name="loop",
        entry_node_id="A",
        nodes=[
            _make_node("A", "agent-a", max_iterations=3, actions=["follow", "return", "finalize"]),
            _make_node("B", "agent-b", actions=["follow", "return"]),
        ],
        edges=[
            # A -> B (incondicional: follow)
            _make_edge("e1", "A", "B"),
            # B -> A (condicional: action == "return")
            _make_edge(
                "e2",
                "B",
                "A",
                condition=EdgeCondition(field="action", operator="eq", value="return"),
            ),
        ],
    )

    # B sempre retorna "return" (loop-back para A).
    fake_worker.set_response(
        "agent-b",
        WorkerResponse(
            status="completed",
            outputs={"feedback": "needs changes"},
            action="return",
            iterations=1,
        ),
    )
    # A sempre retorna "follow" (vai para B).
    fake_worker.set_response(
        "agent-a",
        WorkerResponse(
            status="completed",
            outputs={"code": "v1"},
            action="follow",
            iterations=1,
        ),
    )

    graph = compile_pipeline(pipeline, worker_client=fake_worker, checkpointer=checkpointer)
    config = _config()
    state = initial_state()

    result = await graph.ainvoke(state, config=config)

    # A executou 4 vezes: 3 com worker (iters 0,1,2 < 3) + 1 sem worker
    # (iters=3 >= 3, max_iter_exceeded=True, finalize -> END).
    # O contador de iterations só incrementa quando o worker roda (3 vezes).
    assert result["iterations"]["A"] == 3
    # B executou 3 vezes: após cada uma das 3 execuções de A com worker.
    # Na 4ª execução de A (sem worker), A retorna finalize -> END, B não roda.
    assert result["iterations"]["B"] == 3
    # max_iter_exceeded é True (setado na 4ª execução de A).
    assert result["max_iter_exceeded"] is True
    # Pipeline failed (loop cortado).
    assert result["pipeline_status"] == "failed"


# ---------------------------------------------------------------------------
# Teste 4: Data edge sem flow edge (regra 7)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_data_edge_without_flow_edge(fake_worker: FakeWorker, checkpointer: MemorySaver):
    """Regra 7: data edge sem flow edge injeta flow incondicional.

    A tem uma data edge para B (code_pronto -> code_para_review) mas nenhuma
    flow edge explícita. O compiler injeta uma flow edge incondicional A -> B.
    """
    pipeline = Pipeline(
        id="p4",
        name="data-edge-only",
        entry_node_id="A",
        nodes=[
            _make_node(
                "A",
                "agent-a",
                outputs=[PortDef(name="code_pronto", type="code")],
            ),
            _make_node(
                "B",
                "agent-b",
                inputs=[PortDef(name="code_para_review", type="code", required=True)],
            ),
        ],
        edges=[
            # Somente data edge (sem flow edge explícita).
            _make_edge(
                "e1",
                "A",
                "B",
                type="data",
                data_mapping=DataMapping(
                    source_output="code_pronto",
                    target_input="code_para_review",
                ),
            ),
        ],
    )

    # A produz "code_pronto" (o output que a data edge mapeia).
    fake_worker.set_response(
        "agent-a",
        WorkerResponse(
            status="completed",
            outputs={"code_pronto": "def hello(): pass"},
            action="follow",
            iterations=1,
        ),
    )

    graph = compile_pipeline(pipeline, worker_client=fake_worker, checkpointer=checkpointer)
    config = _config()
    state = initial_state()

    result = await graph.ainvoke(state, config=config)

    # A executou e B executou (flow edge injetada pela regra 7).
    assert result["status"]["A"] == "completed"
    assert result["status"]["B"] == "completed"
    assert result["iterations"]["A"] == 1
    assert result["iterations"]["B"] == 1
    # B recebeu o input de A via dataMapping.
    # O worker de B recebeu "code_para_review" como input.
    b_call = [c for c in fake_worker.calls if c["node_id"] == "B"]
    assert len(b_call) == 1
    assert "code_para_review" in b_call[0]["inputs"]
    assert b_call[0]["inputs"]["code_para_review"] == "def hello(): pass"


# ---------------------------------------------------------------------------
# Teste 5: Aprovação com aprovar e rejeitar
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approval_approve(fake_worker: FakeWorker, checkpointer: MemorySaver):
    """Aprovação: aprovar -> Command(goto=target) -> B executa."""
    pipeline = Pipeline(
        id="p5",
        name="approval-approve",
        entry_node_id="A",
        nodes=[
            _make_node("A", "agent-a"),
            _make_node("B", "agent-b"),
        ],
        edges=[
            _make_edge(
                "e1",
                "A",
                "B",
                requires_approval=True,
                approval_message="Aprovar saída de A?",
            ),
        ],
    )

    graph = compile_pipeline(pipeline, worker_client=fake_worker, checkpointer=checkpointer)
    config = _config()
    state = initial_state()

    # Primeira execução: pausa no nó de aprovação (interrupt).
    # Usamos ainvoke que detecta o interrupt.
    # O LangGraph com MemorySaver salva o checkpoint na pausa.
    # Para detectar a pausa, usamos get_state.
    await graph.ainvoke(state, config=config)

    # Verificar que o grafo está pausado (interrupt).
    snap = graph.get_state(config)
    assert snap is not None
    # O nó de aprovação está em "next" (aguardando resume).
    assert any("approval_node" in n for n in snap.next)

    # Retomar com resume="approved".
    await graph.ainvoke(Command(resume="approved"), config=config)

    # B executou.
    snap = graph.get_state(config)
    assert snap is not None
    assert snap.values["status"]["B"] == "completed"
    assert snap.values["iterations"]["B"] == 1


@pytest.mark.asyncio
async def test_approval_reject(fake_worker: FakeWorker, checkpointer: MemorySaver):
    """Aprovação: rejeitar -> Command(goto=source) -> loop-back para A."""
    pipeline = Pipeline(
        id="p6",
        name="approval-reject",
        entry_node_id="A",
        nodes=[
            _make_node("A", "agent-a", max_iterations=5),
            _make_node("B", "agent-b"),
        ],
        edges=[
            _make_edge(
                "e1",
                "A",
                "B",
                requires_approval=True,
                approval_message="Aprovar?",
                reject_target="A",  # loop-back explícito
            ),
        ],
    )

    graph = compile_pipeline(pipeline, worker_client=fake_worker, checkpointer=checkpointer)
    config = _config()
    state = initial_state()

    # Primeira execução: pausa na aprovação.
    await graph.ainvoke(state, config=config)

    snap = graph.get_state(config)
    assert snap is not None
    assert any("approval_node" in n for n in snap.next)

    # Rejeitar: loop-back para A.
    await graph.ainvoke(Command(resume="rejected"), config=config)

    # A executou de novo (loop-back).
    snap = graph.get_state(config)
    assert snap is not None
    # A executou 2 vezes (1 inicial + 1 loop-back).
    assert snap.values["iterations"]["A"] >= 2


# ---------------------------------------------------------------------------
# Teste 6: Worker fake falhando (grafo não aborta)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_failing_graph_survives(fake_worker: FakeWorker, checkpointer: MemorySaver):
    """ADR-001: worker falha -> nó failed, grafo NÃO aborta."""
    pipeline = Pipeline(
        id="p7",
        name="worker-fail",
        entry_node_id="A",
        nodes=[
            _make_node("A", "agent-a"),
            _make_node("B", "agent-b"),
        ],
        edges=[
            _make_edge("e1", "A", "B"),
        ],
    )

    # Worker sempre falha.
    fake_worker.set_fail(True)

    graph = compile_pipeline(pipeline, worker_client=fake_worker, checkpointer=checkpointer)
    config = _config()
    state = initial_state()

    # O grafo executa mesmo com worker falhando: NÃO levanta exceção.
    result = await graph.ainvoke(state, config=config)

    # A ficou failed.
    assert result["status"]["A"] == "failed"
    assert result["pipeline_status"] == "failed"
    # B também executou (a edge A->B é incondicional, então o grafo segue).
    # B também falhou (worker sempre falha).
    assert result["status"]["B"] == "failed"


# ---------------------------------------------------------------------------
# Teste 7: Determinismo (compilar duas vezes, mesma topologia)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_determinism(fake_worker: FakeWorker):
    """Compilar a mesma pipeline duas vezes gera a mesma topologia."""
    pipeline = Pipeline(
        id="p8",
        name="determinism",
        entry_node_id="A",
        nodes=[
            _make_node("A", "agent-a"),
            _make_node("B", "agent-b"),
            _make_node("C", "agent-c"),
        ],
        edges=[
            _make_edge("e1", "A", "B"),
            _make_edge("e2", "B", "C"),
        ],
    )

    graph1 = compile_pipeline(pipeline, worker_client=fake_worker)
    graph2 = compile_pipeline(pipeline, worker_client=fake_worker)

    # Mesma topologia: mesmos nós.
    nodes1 = set(graph1.nodes.keys())
    nodes2 = set(graph2.nodes.keys())
    assert nodes1 == nodes2

    # Mesmas arestas (edges).
    # O StateGraph compilado tem um grafo interno; comparamos os nós.
    assert "A" in nodes1
    assert "B" in nodes1
    assert "C" in nodes1


# ---------------------------------------------------------------------------
# Teste 8: pipeline_from_dict (parsing JSON)
# ---------------------------------------------------------------------------


def test_pipeline_from_dict():
    """pipeline_from_dict converte JSON da spec 4.2 em Pipeline."""
    d = {
        "id": "p1",
        "name": "test",
        "entryNodeId": "node-1",
        "nodes": [
            {
                "id": "node-1",
                "agentId": "agent-1",
                "agentSnapshot": {
                    "agentId": "agent-1",
                    "name": "Agent 1",
                    "inputs": [{"name": "prompt", "type": "string", "required": True}],
                    "outputs": [{"name": "result", "type": "string"}],
                    "actions": ["follow", "finalize"],
                    "maxIterations": 5,
                },
            },
            {
                "id": "node-2",
                "agentId": "agent-2",
                "agentSnapshot": {
                    "agentId": "agent-2",
                    "name": "Agent 2",
                    "inputs": [{"name": "input", "type": "string"}],
                    "outputs": [],
                    "actions": ["follow"],
                    "maxIterations": 10,
                },
            },
        ],
        "edges": [
            {
                "id": "e1",
                "type": "data",
                "source": "node-1",
                "target": "node-2",
                "dataMapping": {
                    "sourceOutput": "result",
                    "targetInput": "input",
                },
            },
        ],
    }

    pipeline = pipeline_from_dict(d)
    assert pipeline.id == "p1"
    assert pipeline.entry_node_id == "node-1"
    assert len(pipeline.nodes) == 2
    assert pipeline.nodes[0].id == "node-1"
    assert pipeline.nodes[0].agent_snapshot.max_iterations == 5
    assert len(pipeline.edges) == 1
    assert pipeline.edges[0].type == "data"
    assert pipeline.edges[0].data_mapping is not None
    assert pipeline.edges[0].data_mapping.source_output == "result"
    assert pipeline.edges[0].data_mapping.target_input == "input"


# ---------------------------------------------------------------------------
# Teste 9: finalize -> END
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finalize_goes_to_end(fake_worker: FakeWorker, checkpointer: MemorySaver):
    """Action 'finalize' roteia para END (encerra a pipeline)."""
    pipeline = Pipeline(
        id="p9",
        name="finalize",
        entry_node_id="A",
        nodes=[
            _make_node("A", "agent-a", actions=["follow", "finalize"]),
            _make_node("B", "agent-b"),
        ],
        edges=[
            _make_edge("e1", "A", "B"),
        ],
    )

    # A retorna "finalize".
    fake_worker.set_response(
        "agent-a",
        WorkerResponse(
            status="completed",
            outputs={"result": "done"},
            action="finalize",
            iterations=1,
        ),
    )

    graph = compile_pipeline(pipeline, worker_client=fake_worker, checkpointer=checkpointer)
    config = _config()
    state = initial_state()

    result = await graph.ainvoke(state, config=config)

    # A executou e finalizou. B não executou.
    assert result["status"]["A"] == "completed"
    assert result["iterations"]["A"] == 1
    # B não executou (A finalizou).
    assert "B" not in result.get("status", {}) or result["status"].get("B") is None
    assert result["iterations"].get("B", 0) == 0


def test_approval_on_data_edge_is_not_dropped(fake_worker: FakeWorker, checkpointer: MemorySaver):
    """A UI oferece "Requer aprovação" na data edge; a flow edge injetada (regra 7)
    precisa herdar a aprovação, senão o run seguia sem pedir aprovação."""
    pipeline = Pipeline(
        id="p-appr-data",
        name="approval-on-data-edge",
        entry_node_id="A",
        nodes=[
            _make_node("A", "agent-a", outputs=[PortDef(name="spec", type="document")]),
            _make_node("B", "agent-b", inputs=[PortDef(name="spec", type="document")]),
        ],
        edges=[
            _make_edge(
                "e1",
                "A",
                "B",
                type="data",
                requires_approval=True,
                approval_message="Revisar",
                data_mapping=DataMapping(source_output="spec", target_input="spec"),
            )
        ],
    )
    graph = compile_pipeline(pipeline, worker_client=fake_worker, checkpointer=checkpointer)
    assert "approval_node___injected_e1" in graph.get_graph().nodes
