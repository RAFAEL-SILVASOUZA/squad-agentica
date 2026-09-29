"""Integration test for pe-review: compile a complex pipeline with all features.

Covers: approval edge, fan-out, loop with condition, data edge,
and inspects the generated graph topology.

Run with:
    docker compose -p squad-agentica run --rm --no-deps \
        --entrypoint pytest orchestrator tests/test_pe_review_integration.py -v
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
from app.compiler.state import State, initial_state
from app.compiler.validator import validate_pipeline


class FakeWorker:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses: dict[str, WorkerResponse] = {}
        self._default_action: str = "follow"

    def set_response(self, agent_id: str, resp: WorkerResponse) -> None:
        self._responses[agent_id] = resp

    async def execute(
        self,
        agent_id: str,
        node_id: str,
        inputs: dict[str, Any],
        *,
        timeout: int = 60,
        workspace_dir: str | None = None,
        owner_id: str | None = None,
        mcp_servers: list[dict[str, Any]] | None = None,
        run_id: str | None = None,
        mcp_capability: str | None = None,
    ) -> WorkerResponse:
        self.calls.append({"agent_id": agent_id, "node_id": node_id, "inputs": inputs})
        if agent_id in self._responses:
            return self._responses[agent_id]
        outputs = {k: f"{agent_id}:{v}" for k, v in inputs.items()}
        if not outputs:
            outputs["result"] = f"{agent_id}:done"
        return WorkerResponse(
            status="completed",
            outputs=outputs,
            action=self._default_action,
            iterations=1,
        )


def _node(node_id: str, agent_id: str, **kw) -> PipelineNode:
    defaults = dict(
        agent_id=agent_id,
        name=agent_id,
        inputs=kw.pop("inputs", []),
        outputs=kw.pop("outputs", []),
        actions=kw.pop("actions", ["follow"]),
        max_iterations=kw.pop("max_iterations", 10),
        timeout=30,
    )
    return PipelineNode(
        id=node_id,
        agent_id=agent_id,
        agent_snapshot=AgentSnapshot(**defaults),
    )


def _edge(edge_id: str, source: str, target: str, **kw) -> PipelineEdge:
    return PipelineEdge(
        id=edge_id,
        type=kw.pop("type", "flow"),
        source=source,
        target=target,
        condition=kw.pop("condition", None),
        requires_approval=kw.pop("requires_approval", False),
        data_mapping=kw.pop("data_mapping", None),
        reject_target=kw.pop("reject_target", None),
        approval_message=kw.pop("approval_message", None),
        approval_channel=kw.pop("approval_channel", None),
    )


@pytest.fixture
def worker() -> FakeWorker:
    return FakeWorker()


@pytest.fixture
def saver() -> MemorySaver:
    return MemorySaver()


def _config() -> dict[str, Any]:
    return {"configurable": {"thread_id": f"t-{uuid.uuid4().hex[:8]}", "run_id": "run-test"}}


# ---------------------------------------------------------------------------
# Test 1: Complex pipeline with ALL features
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complex_pipeline_all_features(worker: FakeWorker, saver: MemorySaver):
    """Pipeline with: approval edge, fan-out, loop with condition, data edge.

    Topology:
        START -> A (entry)
        A -> approval_node_e1 -> B (approve) / A (reject, loop-back)
        B -> C (flow, unconditional)
        B -> D (flow, unconditional) [fan-out from B]
        C -> A (flow, conditional: action == "return") [loop]
        A -> C (data edge: code -> code_input) [data edge without flow edge -> injects flow]

    Wait, that would create a cycle A->C->A. Let me redesign:

    START -> A (entry)
    A -> approval_node_e1 -> B (approve) / A (reject)
    B -> C (flow, unconditional)
    B -> D (flow, unconditional) [fan-out from B]
    C -> A (flow, conditional: action == "return") [loop back to A]
    A -> C (data edge: code -> code_input) [data edge, no explicit flow A->C]

    Actually the data edge A->C would inject a flow edge A->C (unconditional),
    which conflicts with the approval edge A->approval_node_e1. Let me simplify:

    START -> A (entry)
    A -> approval_node_e1 -> B (approve) / A (reject)
    B -> C (flow, unconditional)
    B -> D (flow, unconditional) [fan-out from B]
    C -> A (flow, conditional: action == "return") [loop]
    C -> E (data edge: result -> input) [data edge, no flow C->E, injects flow]
    """
    pipeline = Pipeline(
        id="p-complex",
        name="complex",
        entry_node_id="A",
        nodes=[
            _node("A", "agent-a", actions=["follow", "return", "finalize"],
                  outputs=[PortDef(name="code", type="code")]),
            _node("B", "agent-b", actions=["follow"]),
            _node("C", "agent-c", actions=["follow", "return"],
                  outputs=[PortDef(name="result", type="string")]),
            _node("D", "agent-d", actions=["follow"]),
            _node("E", "agent-e", actions=["follow"],
                  inputs=[PortDef(name="input", type="string")]),
        ],
        edges=[
            # A -> B with approval
            _edge("e1", "A", "B", requires_approval=True,
                  approval_message="Aprovar?", reject_target="A"),
            # B -> C (unconditional flow)
            _edge("e2", "B", "C"),
            # B -> D (unconditional flow, fan-out)
            _edge("e3", "B", "D"),
            # C -> A (conditional: action == "return", loop)
            _edge("e4", "C", "A",
                  condition=EdgeCondition(field="action", operator="eq", value="return")),
            # C -> E (data edge, no explicit flow -> injects flow)
            _edge("e5", "C", "E", type="data",
                  data_mapping=DataMapping(source_output="result", target_input="input")),
        ],
    )

    # Validate first (criterion 3: validator called before compile).
    result = validate_pipeline(pipeline)
    assert result.is_valid, f"Validation failed: {result.errors}"

    # Compile.
    graph = compile_pipeline(pipeline, worker_client=worker, checkpointer=saver)

    # Inspect graph topology.
    node_names = set(graph.nodes.keys())
    print(f"\nGraph nodes: {sorted(node_names)}")

    # Expected nodes: A, B, C, D, E, approval_node_e1
    assert "A" in node_names
    assert "B" in node_names
    assert "C" in node_names
    assert "D" in node_names
    assert "E" in node_names
    assert "approval_node_e1" in node_names

    # The injected flow edge for C->E (data edge without flow) should be present.
    # C should have conditional edges (for the loop) AND the injected flow to E.
    # In the compiled graph, C's outgoing edges should include A (conditional) and E.

    # Execute: A runs, pauses at approval.
    config = _config()
    state = initial_state()
    await graph.ainvoke(state, config=config)

    snap = graph.get_state(config)
    assert snap is not None
    assert any("approval_node" in n for n in snap.next), f"Expected approval in next, got {snap.next}"

    # Approve: B runs, then fan-out to C and D.
    await graph.ainvoke(Command(resume="approved"), config=config)

    snap = graph.get_state(config)
    assert snap is not None
    vals = snap.values

    # B completed.
    assert vals["status"]["B"] == "completed"
    # C and D both ran (fan-out).
    assert vals["status"]["C"] == "completed"
    assert vals["status"]["D"] == "completed"
    # E ran (injected flow from data edge C->E).
    assert vals["status"]["E"] == "completed"

    # C returned "follow" (default), so no loop. Pipeline should be done.
    # Check that the graph finished (no next nodes).
    assert len(snap.next) == 0, f"Expected no next nodes, got {snap.next}"

    # Verify data edge: E received C's output via dataMapping.
    e_calls = [c for c in worker.calls if c["node_id"] == "E"]
    assert len(e_calls) == 1
    assert "input" in e_calls[0]["inputs"]


# ---------------------------------------------------------------------------
# Test 2: Loop with condition (C returns "return" -> loop back to A)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loop_condition(worker: FakeWorker, saver: MemorySaver):
    """Loop: C returns 'return' -> goes back to A. maxIterations cuts the loop."""
    pipeline = Pipeline(
        id="p-loop",
        name="loop-test",
        entry_node_id="A",
        nodes=[
            _node("A", "agent-a", actions=["follow", "return", "finalize"],
                  max_iterations=3),
            _node("C", "agent-c", actions=["follow", "return"]),
        ],
        edges=[
            _edge("e1", "A", "C"),
            _edge("e2", "C", "A",
                  condition=EdgeCondition(field="action", operator="eq", value="return")),
        ],
    )

    # C always returns "return" (loop back to A).
    worker.set_response("agent-c", WorkerResponse(
        status="completed", outputs={"result": "needs fix"}, action="return", iterations=1,
    ))
    # A always returns "follow" (goes to C).
    worker.set_response("agent-a", WorkerResponse(
        status="completed", outputs={"code": "v1"}, action="follow", iterations=1,
    ))

    graph = compile_pipeline(pipeline, worker_client=worker, checkpointer=saver)
    config = _config()
    state = initial_state()

    result = await graph.ainvoke(state, config=config)

    # A ran 3 times (max_iterations=3), then on the 4th call it detects
    # iters >= max and returns finalize -> END.
    assert result["iterations"]["A"] == 3
    assert result["iterations"]["C"] == 3
    assert result["max_iter_exceeded"] is True
    assert result["pipeline_status"] == "failed"


# ---------------------------------------------------------------------------
# Test 3: Fan-out with data edges to different targets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fan_out_with_data_edges(worker: FakeWorker, saver: MemorySaver):
    """Fan-out: A -> B and A -> C (parallel). Data edge A->B only."""
    pipeline = Pipeline(
        id="p-fanout-data",
        name="fanout-data",
        entry_node_id="A",
        nodes=[
            _node("A", "agent-a", outputs=[PortDef(name="data", type="string")]),
            _node("B", "agent-b", inputs=[PortDef(name="input", type="string")]),
            _node("C", "agent-c"),
        ],
        edges=[
            # Flow edges for fan-out.
            _edge("e1", "A", "B"),
            _edge("e2", "A", "C"),
            # Data edge A->B (code -> input).
            _edge("e3", "A", "B", type="data",
                  data_mapping=DataMapping(source_output="data", target_input="input")),
        ],
    )

    worker.set_response("agent-a", WorkerResponse(
        status="completed", outputs={"data": "hello"}, action="follow", iterations=1,
    ))

    graph = compile_pipeline(pipeline, worker_client=worker, checkpointer=saver)
    config = _config()
    state = initial_state()

    result = await graph.ainvoke(state, config=config)

    # All three ran.
    assert result["status"]["A"] == "completed"
    assert result["status"]["B"] == "completed"
    assert result["status"]["C"] == "completed"

    # B received the data from A.
    b_calls = [c for c in worker.calls if c["node_id"] == "B"]
    assert len(b_calls) == 1
    assert b_calls[0]["inputs"].get("input") == "hello"

    # C did NOT receive data (no data edge A->C).
    c_calls = [c for c in worker.calls if c["node_id"] == "C"]
    assert len(c_calls) == 1
    assert "input" not in c_calls[0]["inputs"]


# ---------------------------------------------------------------------------
# Test 4: Determinism (same JSON -> same graph)
# ---------------------------------------------------------------------------


def test_determinism_same_json_same_graph(worker: FakeWorker):
    """Compiling the same pipeline JSON twice produces identical topology."""
    d = {
        "id": "p-det",
        "name": "determinism",
        "entryNodeId": "A",
        "nodes": [
            {"id": "A", "agentId": "a1", "agentSnapshot": {
                "agentId": "a1", "name": "A", "inputs": [], "outputs": [],
                "actions": ["follow"], "maxIterations": 5,
            }},
            {"id": "B", "agentId": "a2", "agentSnapshot": {
                "agentId": "a2", "name": "B", "inputs": [], "outputs": [],
                "actions": ["follow"], "maxIterations": 5,
            }},
        ],
        "edges": [
            {"id": "e1", "type": "flow", "source": "A", "target": "B"},
        ],
    }

    p1 = pipeline_from_dict(d)
    p2 = pipeline_from_dict(d)

    g1 = compile_pipeline(p1, worker_client=worker)
    g2 = compile_pipeline(p2, worker_client=worker)

    assert set(g1.nodes.keys()) == set(g2.nodes.keys())
    assert "A" in g1.nodes
    assert "B" in g1.nodes


# ---------------------------------------------------------------------------
# Test 5: Validator format matches spec 4.2
# ---------------------------------------------------------------------------


def test_validator_format_spec_4_2():
    """Validator output matches {"errors": [{"rule", "message", "nodeId"?, "edgeId"?}]}."""
    pipeline = Pipeline(
        id="p-fmt",
        name="format-test",
        entry_node_id="nonexistent",  # rule 9 violation
        nodes=[
            _node("A", "agent-a"),
        ],
        edges=[],
    )

    result = validate_pipeline(pipeline)
    d = result.to_dict()

    assert "errors" in d
    assert isinstance(d["errors"], list)
    assert len(d["errors"]) > 0

    for err in d["errors"]:
        assert "rule" in err
        assert "message" in err
        assert isinstance(err["rule"], int)
        assert isinstance(err["message"], str)

    # Rule 9 should be present.
    rules = [e["rule"] for e in d["errors"]]
    assert 9 in rules


# ---------------------------------------------------------------------------
# Test 6: State is JSON-serializable (criterion for PostgresSaver)
# ---------------------------------------------------------------------------


def test_state_json_serializable():
    """All State values must be JSON-serializable for PostgresSaver."""
    import json

    state = initial_state()
    # Simulate a full state after execution.
    state["data"] = {"A": {"code": "def hello(): pass"}, "B": {"result": 42}}
    state["actions"] = {"A": "follow", "B": "finalize"}
    state["status"] = {"A": "completed", "B": "completed"}
    state["iterations"] = {"A": 2, "B": 1}
    state["max_iter_exceeded"] = False
    state["pipeline_status"] = "running"

    # Must serialize without error.
    serialized = json.dumps(state)
    deserialized = json.loads(serialized)
    assert deserialized == state


# ---------------------------------------------------------------------------
# Test 7: Approval node uses real node IDs (not labels)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approval_uses_real_node_ids(worker: FakeWorker, saver: MemorySaver):
    """ADR-006: Command(goto=...) uses real node IDs, not 'proceed'/'reject_handler'."""
    pipeline = Pipeline(
        id="p-approval-ids",
        name="approval-ids",
        entry_node_id="A",
        nodes=[
            _node("A", "agent-a"),
            _node("B", "agent-b"),
        ],
        edges=[
            _edge("e1", "A", "B", requires_approval=True,
                  approval_message="Aprovar?", reject_target="A"),
        ],
    )

    graph = compile_pipeline(pipeline, worker_client=worker, checkpointer=saver)

    # The approval node should be in the graph.
    assert "approval_node_e1" in graph.nodes

    # Execute and pause at approval.
    config = _config()
    state = initial_state()
    await graph.ainvoke(state, config=config)

    snap = graph.get_state(config)
    assert snap is not None
    # The next node should be the approval node.
    assert "approval_node_e1" in snap.next

    # Approve: should go to B (real node ID).
    await graph.ainvoke(Command(resume="approved"), config=config)
    snap = graph.get_state(config)
    assert snap is not None
    assert snap.values["status"]["B"] == "completed"

    # Now test reject: new pipeline, reject -> loop back to A.
    pipeline2 = Pipeline(
        id="p-approval-reject",
        name="approval-reject",
        entry_node_id="A",
        nodes=[
            _node("A", "agent-a", max_iterations=5),
            _node("B", "agent-b"),
        ],
        edges=[
            _edge("e1", "A", "B", requires_approval=True,
                  approval_message="Aprovar?", reject_target="A"),
        ],
    )
    graph2 = compile_pipeline(pipeline2, worker_client=worker, checkpointer=saver)
    config2 = _config()
    await graph2.ainvoke(initial_state(), config=config2)

    snap2 = graph2.get_state(config2)
    assert snap2 is not None
    assert "approval_node_e1" in snap2.next

    # Reject: should go back to A (real node ID).
    await graph2.ainvoke(Command(resume="rejected"), config=config2)
    snap3 = graph2.get_state(config2)
    assert snap3 is not None
    # A should have run again (loop-back).
    assert snap3.values["iterations"]["A"] >= 2
