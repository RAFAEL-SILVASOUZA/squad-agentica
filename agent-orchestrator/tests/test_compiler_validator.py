"""Testes do pipeline validator (validator.py).

Cobrem as 11 regras da spec 4.2 + D5 5.2:
  - Regra 1: data edge exige dataMapping
  - Regra 2: sourceOutput existe em outputs
  - Regra 3: targetInput existe em inputs
  - Regra 4: tipo do port compatível
  - Regra 5: data edge pra B e flow edge pra C (não é erro)
  - Regra 6: inputs required sem data edge → rejeitar
  - Regra 7: data edge sem flow edge → injeta flow (transformação)
  - Regra 8: nó órfão → rejeitar
  - Regra 9: entryNodeId inexistente → rejeitar
  - Regra 10: action sem flow edge → aviso
  - Regra 11: flow edges duplicadas → rejeitar

Rode com:
    docker compose -p squad-agentica run --rm --no-deps \
        --entrypoint pytest orchestrator tests/test_compiler_validator.py -v
"""

from __future__ import annotations

from app.compiler.graph_builder import (
    AgentSnapshot,
    DataMapping,
    EdgeCondition,
    Pipeline,
    PipelineEdge,
    PipelineNode,
    PortDef,
)
from app.compiler.validator import validate_pipeline  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers para construir pipelines de teste
# ---------------------------------------------------------------------------


def _make_snapshot(
    agent_id: str = "agent-1",
    *,
    inputs: list[PortDef] | None = None,
    outputs: list[PortDef] | None = None,
    actions: list[str] | None = None,
) -> AgentSnapshot:
    return AgentSnapshot(
        agent_id=agent_id,
        name=agent_id,
        inputs=inputs or [],
        outputs=outputs or [],
        actions=actions or ["follow"],
        max_iterations=10,
        timeout=30,
    )


def _make_node(
    node_id: str,
    agent_id: str = "agent-1",
    *,
    inputs: list[PortDef] | None = None,
    outputs: list[PortDef] | None = None,
    actions: list[str] | None = None,
) -> PipelineNode:
    return PipelineNode(
        id=node_id,
        agent_id=agent_id,
        agent_snapshot=_make_snapshot(
            agent_id, inputs=inputs, outputs=outputs, actions=actions
        ),
    )


def _make_edge(
    edge_id: str,
    source: str,
    target: str,
    *,
    type: str = "flow",
    condition: EdgeCondition | None = None,
    data_mapping: DataMapping | None = None,
    requires_approval: bool = False,
) -> PipelineEdge:
    return PipelineEdge(
        id=edge_id,
        type=type,
        source=source,
        target=target,
        condition=condition,
        data_mapping=data_mapping,
        requires_approval=requires_approval,
    )


def _simple_pipeline() -> Pipeline:
    """Pipeline válida simples: A -> B (flow edge)."""
    return Pipeline(
        id="p1",
        name="simple",
        entry_node_id="A",
        nodes=[
            _make_node("A", "agent-a"),
            _make_node("B", "agent-b"),
        ],
        edges=[
            _make_edge("e1", "A", "B"),
        ],
    )


# ---------------------------------------------------------------------------
# Regra 1: Data edge exige dataMapping
# ---------------------------------------------------------------------------


def test_rule_1_valid_data_edge():
    """Data edge com dataMapping válido não gera erro."""
    pipeline = Pipeline(
        id="p1",
        name="r1-valid",
        entry_node_id="A",
        nodes=[
            _make_node(
                "A",
                "agent-a",
                outputs=[PortDef(name="result", type="string")],
            ),
            _make_node(
                "B",
                "agent-b",
                inputs=[PortDef(name="input", type="string")],
            ),
        ],
        edges=[
            _make_edge(
                "e1",
                "A",
                "B",
                type="data",
                data_mapping=DataMapping(source_output="result", target_input="input"),
            ),
        ],
    )
    result = validate_pipeline(pipeline)
    r1_errors = [e for e in result.errors if e.rule == 1]
    assert r1_errors == []


def test_rule_1_missing_data_mapping():
    """Data edge sem dataMapping gera erro regra 1."""
    pipeline = Pipeline(
        id="p1",
        name="r1-invalid",
        entry_node_id="A",
        nodes=[
            _make_node("A", "agent-a"),
            _make_node("B", "agent-b"),
        ],
        edges=[
            _make_edge("e1", "A", "B", type="data"),  # sem data_mapping
        ],
    )
    result = validate_pipeline(pipeline)
    r1_errors = [e for e in result.errors if e.rule == 1]
    assert len(r1_errors) == 1
    assert "missing dataMapping" in r1_errors[0].message


def test_rule_1_empty_source_output():
    """Data edge com sourceOutput vazio gera erro regra 1."""
    pipeline = Pipeline(
        id="p1",
        name="r1-empty-src",
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
                type="data",
                data_mapping=DataMapping(source_output="", target_input="input"),
            ),
        ],
    )
    result = validate_pipeline(pipeline)
    r1_errors = [e for e in result.errors if e.rule == 1]
    assert len(r1_errors) == 1
    assert "empty sourceOutput" in r1_errors[0].message


# ---------------------------------------------------------------------------
# Regra 2: sourceOutput existe em outputs do agente source
# ---------------------------------------------------------------------------


def test_rule_2_valid_source_output():
    """sourceOutput existe em outputs do agente: não gera erro."""
    pipeline = Pipeline(
        id="p1",
        name="r2-valid",
        entry_node_id="A",
        nodes=[
            _make_node(
                "A",
                "agent-a",
                outputs=[PortDef(name="result", type="string")],
            ),
            _make_node(
                "B",
                "agent-b",
                inputs=[PortDef(name="input", type="string")],
            ),
        ],
        edges=[
            _make_edge(
                "e1",
                "A",
                "B",
                type="data",
                data_mapping=DataMapping(source_output="result", target_input="input"),
            ),
        ],
    )
    result = validate_pipeline(pipeline)
    r2_errors = [e for e in result.errors if e.rule == 2]
    assert r2_errors == []


def test_rule_2_invalid_source_output():
    """sourceOutput não existe em outputs do agente: gera erro regra 2."""
    pipeline = Pipeline(
        id="p1",
        name="r2-invalid",
        entry_node_id="A",
        nodes=[
            _make_node(
                "A",
                "agent-a",
                outputs=[PortDef(name="result", type="string")],
            ),
            _make_node(
                "B",
                "agent-b",
                inputs=[PortDef(name="input", type="string")],
            ),
        ],
        edges=[
            _make_edge(
                "e1",
                "A",
                "B",
                type="data",
                data_mapping=DataMapping(source_output="nonexistent", target_input="input"),
            ),
        ],
    )
    result = validate_pipeline(pipeline)
    r2_errors = [e for e in result.errors if e.rule == 2]
    assert len(r2_errors) == 1
    assert "nonexistent" in r2_errors[0].message


# ---------------------------------------------------------------------------
# Regra 3: targetInput existe em inputs do agente target
# ---------------------------------------------------------------------------


def test_rule_3_valid_target_input():
    """targetInput existe em inputs do agente: não gera erro."""
    pipeline = Pipeline(
        id="p1",
        name="r3-valid",
        entry_node_id="A",
        nodes=[
            _make_node(
                "A",
                "agent-a",
                outputs=[PortDef(name="result", type="string")],
            ),
            _make_node(
                "B",
                "agent-b",
                inputs=[PortDef(name="input", type="string")],
            ),
        ],
        edges=[
            _make_edge(
                "e1",
                "A",
                "B",
                type="data",
                data_mapping=DataMapping(source_output="result", target_input="input"),
            ),
        ],
    )
    result = validate_pipeline(pipeline)
    r3_errors = [e for e in result.errors if e.rule == 3]
    assert r3_errors == []


def test_rule_3_invalid_target_input():
    """targetInput não existe em inputs do agente: gera erro regra 3."""
    pipeline = Pipeline(
        id="p1",
        name="r3-invalid",
        entry_node_id="A",
        nodes=[
            _make_node(
                "A",
                "agent-a",
                outputs=[PortDef(name="result", type="string")],
            ),
            _make_node(
                "B",
                "agent-b",
                inputs=[PortDef(name="input", type="string")],
            ),
        ],
        edges=[
            _make_edge(
                "e1",
                "A",
                "B",
                type="data",
                data_mapping=DataMapping(source_output="result", target_input="nonexistent"),
            ),
        ],
    )
    result = validate_pipeline(pipeline)
    r3_errors = [e for e in result.errors if e.rule == 3]
    assert len(r3_errors) == 1
    assert "nonexistent" in r3_errors[0].message


# ---------------------------------------------------------------------------
# Regra 4: Tipo do port compatível
# ---------------------------------------------------------------------------


def test_rule_4_compatible_types():
    """Tipos iguais: não gera erro."""
    pipeline = Pipeline(
        id="p1",
        name="r4-valid",
        entry_node_id="A",
        nodes=[
            _make_node(
                "A",
                "agent-a",
                outputs=[PortDef(name="result", type="code")],
            ),
            _make_node(
                "B",
                "agent-b",
                inputs=[PortDef(name="input", type="code")],
            ),
        ],
        edges=[
            _make_edge(
                "e1",
                "A",
                "B",
                type="data",
                data_mapping=DataMapping(source_output="result", target_input="input"),
            ),
        ],
    )
    result = validate_pipeline(pipeline)
    r4_errors = [e for e in result.errors if e.rule == 4]
    assert r4_errors == []


def test_rule_4_incompatible_types():
    """Tipos diferentes: gera erro regra 4."""
    pipeline = Pipeline(
        id="p1",
        name="r4-invalid",
        entry_node_id="A",
        nodes=[
            _make_node(
                "A",
                "agent-a",
                outputs=[PortDef(name="result", type="code")],
            ),
            _make_node(
                "B",
                "agent-b",
                inputs=[PortDef(name="input", type="string")],
            ),
        ],
        edges=[
            _make_edge(
                "e1",
                "A",
                "B",
                type="data",
                data_mapping=DataMapping(source_output="result", target_input="input"),
            ),
        ],
    )
    result = validate_pipeline(pipeline)
    r4_errors = [e for e in result.errors if e.rule == 4]
    assert len(r4_errors) == 1
    assert "type mismatch" in r4_errors[0].message


# ---------------------------------------------------------------------------
# Regra 5: Data edge pra B e flow edge pra C (não é erro)
# ---------------------------------------------------------------------------


def test_rule_5_different_targets_not_error():
    """Agente A tem data edge pra B e flow edge pra C: não é erro."""
    pipeline = Pipeline(
        id="p1",
        name="r5-valid",
        entry_node_id="A",
        nodes=[
            _make_node(
                "A",
                "agent-a",
                outputs=[PortDef(name="result", type="string")],
            ),
            _make_node(
                "B",
                "agent-b",
                inputs=[PortDef(name="input", type="string")],
            ),
            _make_node("C", "agent-c"),
        ],
        edges=[
            # Data edge A -> B
            _make_edge(
                "e1",
                "A",
                "B",
                type="data",
                data_mapping=DataMapping(source_output="result", target_input="input"),
            ),
            # Flow edge A -> C
            _make_edge("e2", "A", "C", type="flow"),
        ],
    )
    result = validate_pipeline(pipeline)
    # Regra 5 nunca gera erro.
    r5_errors = [e for e in result.errors if e.rule == 5]
    assert r5_errors == []
    # O grafo é válido (sem erros).
    assert result.is_valid


# ---------------------------------------------------------------------------
# Regra 6: Inputs required sem data edge → rejeitar
# ---------------------------------------------------------------------------


def test_rule_6_required_input_served():
    """Input required atendido por data edge: não gera erro."""
    pipeline = Pipeline(
        id="p1",
        name="r6-valid",
        entry_node_id="A",
        nodes=[
            _make_node(
                "A",
                "agent-a",
                outputs=[PortDef(name="result", type="string")],
            ),
            _make_node(
                "B",
                "agent-b",
                inputs=[PortDef(name="input", type="string", required=True)],
            ),
        ],
        edges=[
            _make_edge(
                "e1",
                "A",
                "B",
                type="data",
                data_mapping=DataMapping(source_output="result", target_input="input"),
            ),
        ],
    )
    result = validate_pipeline(pipeline)
    r6_errors = [e for e in result.errors if e.rule == 6]
    assert r6_errors == []


def test_rule_6_required_input_not_served():
    """Input required sem data edge: gera erro regra 6."""
    pipeline = Pipeline(
        id="p1",
        name="r6-invalid",
        entry_node_id="A",
        nodes=[
            _make_node("A", "agent-a"),
            _make_node(
                "B",
                "agent-b",
                inputs=[PortDef(name="input", type="string", required=True)],
            ),
        ],
        edges=[
            _make_edge("e1", "A", "B", type="flow"),  # só flow, sem data
        ],
    )
    result = validate_pipeline(pipeline)
    r6_errors = [e for e in result.errors if e.rule == 6]
    assert len(r6_errors) == 1
    assert "required input" in r6_errors[0].message
    assert "input" in r6_errors[0].message


def test_rule_6_optional_input_not_served_ok():
    """Input optional sem data edge: não gera erro."""
    pipeline = Pipeline(
        id="p1",
        name="r6-optional",
        entry_node_id="A",
        nodes=[
            _make_node("A", "agent-a"),
            _make_node(
                "B",
                "agent-b",
                inputs=[PortDef(name="input", type="string", required=False)],
            ),
        ],
        edges=[
            _make_edge("e1", "A", "B", type="flow"),
        ],
    )
    result = validate_pipeline(pipeline)
    r6_errors = [e for e in result.errors if e.rule == 6]
    assert r6_errors == []


# ---------------------------------------------------------------------------
# Regra 7: Data edge sem flow edge → injeta flow (transformação)
# ---------------------------------------------------------------------------


def test_rule_7_injects_flow_edge():
    """Data edge sem flow edge explícita: injeta flow incondicional."""
    pipeline = Pipeline(
        id="p1",
        name="r7-inject",
        entry_node_id="A",
        nodes=[
            _make_node(
                "A",
                "agent-a",
                outputs=[PortDef(name="result", type="string")],
            ),
            _make_node(
                "B",
                "agent-b",
                inputs=[PortDef(name="input", type="string")],
            ),
        ],
        edges=[
            _make_edge(
                "e1",
                "A",
                "B",
                type="data",
                data_mapping=DataMapping(source_output="result", target_input="input"),
            ),
        ],
    )
    result = validate_pipeline(pipeline)
    # Regra 7 não gera erro.
    r7_errors = [e for e in result.errors if e.rule == 7]
    assert r7_errors == []
    # Injeta uma flow edge.
    assert len(result.injected_flow_edges) == 1
    injected = result.injected_flow_edges[0]
    assert injected.type == "flow"
    assert injected.source == "A"
    assert injected.target == "B"
    assert injected.condition is None


def test_rule_7_no_injection_if_flow_exists():
    """Data edge com flow edge explícita entre o mesmo par: não injeta."""
    pipeline = Pipeline(
        id="p1",
        name="r7-no-inject",
        entry_node_id="A",
        nodes=[
            _make_node(
                "A",
                "agent-a",
                outputs=[PortDef(name="result", type="string")],
            ),
            _make_node(
                "B",
                "agent-b",
                inputs=[PortDef(name="input", type="string")],
            ),
        ],
        edges=[
            _make_edge("e1", "A", "B", type="flow"),  # flow edge explícita
            _make_edge(
                "e2",
                "A",
                "B",
                type="data",
                data_mapping=DataMapping(source_output="result", target_input="input"),
            ),
        ],
    )
    result = validate_pipeline(pipeline)
    # Não injeta (já existe flow edge).
    assert len(result.injected_flow_edges) == 0


# ---------------------------------------------------------------------------
# Regra 8: Nó órfão → rejeitar
# ---------------------------------------------------------------------------


def test_rule_8_no_orphans():
    """Todos os nós têm entrada (exceto entry): não gera erro."""
    pipeline = Pipeline(
        id="p1",
        name="r8-valid",
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
    result = validate_pipeline(pipeline)
    r8_errors = [e for e in result.errors if e.rule == 8]
    assert r8_errors == []


def test_rule_8_orphan_node():
    """Nó sem entrada (e não é entry): gera erro regra 8."""
    pipeline = Pipeline(
        id="p1",
        name="r8-invalid",
        entry_node_id="A",
        nodes=[
            _make_node("A", "agent-a"),
            _make_node("B", "agent-b"),
            _make_node("C", "agent-c"),  # órfão
        ],
        edges=[
            _make_edge("e1", "A", "B"),
        ],
    )
    result = validate_pipeline(pipeline)
    r8_errors = [e for e in result.errors if e.rule == 8]
    assert len(r8_errors) == 1
    assert "orphan" in r8_errors[0].message
    assert r8_errors[0].node_id == "C"


def test_rule_8_data_edge_counts_as_incoming():
    """Data edge de entrada conta como incoming válido (regra 8)."""
    pipeline = Pipeline(
        id="p1",
        name="r8-data-incoming",
        entry_node_id="A",
        nodes=[
            _make_node(
                "A",
                "agent-a",
                outputs=[PortDef(name="result", type="string")],
            ),
            _make_node(
                "B",
                "agent-b",
                inputs=[PortDef(name="input", type="string")],
            ),
        ],
        edges=[
            # Só data edge (sem flow edge explícita).
            _make_edge(
                "e1",
                "A",
                "B",
                type="data",
                data_mapping=DataMapping(source_output="result", target_input="input"),
            ),
        ],
    )
    result = validate_pipeline(pipeline)
    r8_errors = [e for e in result.errors if e.rule == 8]
    assert r8_errors == []


# ---------------------------------------------------------------------------
# Regra 9: entryNodeId referencia nó existente
# ---------------------------------------------------------------------------


def test_rule_9_valid_entry():
    """entryNodeId referencia nó existente: não gera erro."""
    pipeline = _simple_pipeline()
    result = validate_pipeline(pipeline)
    r9_errors = [e for e in result.errors if e.rule == 9]
    assert r9_errors == []


def test_rule_9_invalid_entry():
    """entryNodeId não referencia nó existente: gera erro regra 9."""
    pipeline = Pipeline(
        id="p1",
        name="r9-invalid",
        entry_node_id="NONEXISTENT",
        nodes=[
            _make_node("A", "agent-a"),
            _make_node("B", "agent-b"),
        ],
        edges=[
            _make_edge("e1", "A", "B"),
        ],
    )
    result = validate_pipeline(pipeline)
    r9_errors = [e for e in result.errors if e.rule == 9]
    assert len(r9_errors) == 1
    assert "NONEXISTENT" in r9_errors[0].message


def test_rule_9_empty_entry():
    """entryNodeId vazio: gera erro regra 9."""
    pipeline = Pipeline(
        id="p1",
        name="r9-empty",
        entry_node_id="",
        nodes=[
            _make_node("A", "agent-a"),
        ],
        edges=[],
    )
    result = validate_pipeline(pipeline)
    r9_errors = [e for e in result.errors if e.rule == 9]
    assert len(r9_errors) == 1


# ---------------------------------------------------------------------------
# Regra 10: Action sem flow edge → aviso (não erro)
# ---------------------------------------------------------------------------


def test_rule_10_action_with_flow_edge():
    """Action 'return' com flow edge condicional: não gera aviso."""
    pipeline = Pipeline(
        id="p1",
        name="r10-valid",
        entry_node_id="A",
        nodes=[
            _make_node("A", "agent-a", actions=["follow", "return", "finalize"]),
            _make_node("B", "agent-b"),
        ],
        edges=[
            _make_edge("e1", "A", "B"),  # follow (incondicional)
            _make_edge(
                "e2",
                "A",
                "A",
                condition=EdgeCondition(field="action", operator="eq", value="return"),
            ),  # return -> loop
        ],
    )
    result = validate_pipeline(pipeline)
    r10_warnings = [w for w in result.warnings if w.rule == 10]
    assert r10_warnings == []


def test_rule_10_action_without_flow_edge():
    """Action 'return' sem flow edge condicional: gera aviso (não erro)."""
    pipeline = Pipeline(
        id="p1",
        name="r10-warning",
        entry_node_id="A",
        nodes=[
            _make_node("A", "agent-a", actions=["follow", "return", "finalize"]),
            _make_node("B", "agent-b"),
        ],
        edges=[
            _make_edge("e1", "A", "B"),  # só follow
        ],
    )
    result = validate_pipeline(pipeline)
    # Não é erro.
    r10_errors = [e for e in result.errors if e.rule == 10]
    assert r10_errors == []
    # É aviso.
    r10_warnings = [w for w in result.warnings if w.rule == 10]
    assert len(r10_warnings) == 1
    assert "return" in r10_warnings[0].message
    # O grafo é válido (sem erros).
    assert result.is_valid


def test_rule_10_follow_and_finalize_never_warn():
    """Actions 'follow' e 'finalize' nunca geram aviso."""
    pipeline = Pipeline(
        id="p1",
        name="r10-follow-finalize",
        entry_node_id="A",
        nodes=[
            _make_node("A", "agent-a", actions=["follow", "finalize"]),
            _make_node("B", "agent-b"),
        ],
        edges=[
            _make_edge("e1", "A", "B"),
        ],
    )
    result = validate_pipeline(pipeline)
    r10_warnings = [w for w in result.warnings if w.rule == 10]
    assert r10_warnings == []


# ---------------------------------------------------------------------------
# Regra 11: Flow edges duplicadas → rejeitar
# ---------------------------------------------------------------------------


def test_rule_11_different_conditions_ok():
    """Múltiplas flow edges com conditions diferentes: permitido (branching)."""
    pipeline = Pipeline(
        id="p1",
        name="r11-branching",
        entry_node_id="A",
        nodes=[
            _make_node("A", "agent-a", actions=["follow", "return", "finalize"]),
            _make_node("B", "agent-b"),
            _make_node("C", "agent-c"),
        ],
        edges=[
            _make_edge(
                "e1",
                "A",
                "B",
                condition=EdgeCondition(field="action", operator="eq", value="follow"),
            ),
            _make_edge(
                "e2",
                "A",
                "C",
                condition=EdgeCondition(field="action", operator="eq", value="return"),
            ),
        ],
    )
    result = validate_pipeline(pipeline)
    r11_errors = [e for e in result.errors if e.rule == 11]
    assert r11_errors == []


def test_rule_11_duplicate_flow_edges():
    """Duas flow edges idênticas (mesma condition) entre o mesmo par: rejeitar."""
    pipeline = Pipeline(
        id="p1",
        name="r11-duplicate",
        entry_node_id="A",
        nodes=[
            _make_node("A", "agent-a"),
            _make_node("B", "agent-b"),
        ],
        edges=[
            _make_edge("e1", "A", "B"),  # incondicional
            _make_edge("e2", "A", "B"),  # idêntica (incondicional)
        ],
    )
    result = validate_pipeline(pipeline)
    r11_errors = [e for e in result.errors if e.rule == 11]
    assert len(r11_errors) == 1
    assert "Duplicate" in r11_errors[0].message


def test_rule_11_same_condition_different_pairs_ok():
    """Mesma condition em pares diferentes: permitido."""
    pipeline = Pipeline(
        id="p1",
        name="r11-different-pairs",
        entry_node_id="A",
        nodes=[
            _make_node("A", "agent-a"),
            _make_node("B", "agent-b"),
            _make_node("C", "agent-c"),
            _make_node("D", "agent-d"),
        ],
        edges=[
            _make_edge(
                "e1",
                "A",
                "B",
                condition=EdgeCondition(field="action", operator="eq", value="follow"),
            ),
            _make_edge(
                "e2",
                "C",
                "D",
                condition=EdgeCondition(field="action", operator="eq", value="follow"),
            ),
            _make_edge("e3", "A", "C"),  # para conectar C
        ],
    )
    result = validate_pipeline(pipeline)
    r11_errors = [e for e in result.errors if e.rule == 11]
    assert r11_errors == []


# ---------------------------------------------------------------------------
# Grafo real do editor com aviso de action sem aresta
# ---------------------------------------------------------------------------


def test_real_editor_graph_with_action_warning():
    """Grafo realista do editor: A -> B -> C com action 'return' sem edge.

    Simula o caso comum: o agente A declara actions ['follow', 'return', 'finalize']
    mas o editor só desenhou a flow edge A -> B (follow). O 'return' não tem
    edge condicional → aviso (não erro).
    """
    pipeline = Pipeline(
        id="p-editor",
        name="editor-graph",
        entry_node_id="A",
        nodes=[
            _make_node(
                "A",
                "agent-coder",
                outputs=[PortDef(name="code", type="code")],
                actions=["follow", "return", "finalize"],
            ),
            _make_node(
                "B",
                "agent-reviewer",
                inputs=[PortDef(name="code_to_review", type="code", required=True)],
                outputs=[PortDef(name="feedback", type="string")],
                actions=["follow", "return"],
            ),
            _make_node(
                "C",
                "agent-deployer",
                inputs=[PortDef(name="code", type="code")],
                actions=["follow", "finalize"],
            ),
        ],
        edges=[
            # A -> B: data edge (code -> code_to_review) + flow edge implícita (regra 7)
            _make_edge(
                "e1",
                "A",
                "B",
                type="data",
                data_mapping=DataMapping(source_output="code", target_input="code_to_review"),
            ),
            # B -> C: data edge (feedback -> code? não, vamos usar flow + data)
            # B -> C: flow edge
            _make_edge("e2", "B", "C", type="flow"),
            # B tem action 'return' mas não há flow edge condicional para 'return'
            # → aviso regra 10
        ],
    )
    result = validate_pipeline(pipeline)

    # O grafo é válido (sem erros).
    assert result.is_valid
    # Há avisos para o action 'return' dos nós A e B (nenhum tem flow edge condicional).
    r10_warnings = [w for w in result.warnings if w.rule == 10]
    assert len(r10_warnings) == 2
    warned_nodes = {w.node_id for w in r10_warnings}
    assert warned_nodes == {"A", "B"}
    for w in r10_warnings:
        assert "return" in w.message
    # Regra 7 injetou uma flow edge para A -> B.
    assert len(result.injected_flow_edges) == 1
    assert result.injected_flow_edges[0].source == "A"
    assert result.injected_flow_edges[0].target == "B"


# ---------------------------------------------------------------------------
# Pipeline totalmente válida (sem erros nem avisos)
# ---------------------------------------------------------------------------


def test_fully_valid_pipeline():
    """Pipeline simples e válida: nenhum erro, nenhum aviso."""
    pipeline = _simple_pipeline()
    result = validate_pipeline(pipeline)
    assert result.is_valid
    assert result.errors == []
    assert result.warnings == []
    assert result.injected_flow_edges == []


# ---------------------------------------------------------------------------
# Múltiplas violações simultâneas
# ---------------------------------------------------------------------------


def test_multiple_violations():
    """Pipeline com múltiplas violações: todas são reportadas."""
    pipeline = Pipeline(
        id="p1",
        name="multi-violation",
        entry_node_id="NONEXISTENT",  # regra 9
        nodes=[
            _make_node(
                "A",
                "agent-a",
                outputs=[PortDef(name="result", type="code")],
            ),
            _make_node(
                "B",
                "agent-b",
                inputs=[PortDef(name="input", type="string", required=True)],
            ),
            _make_node("C", "agent-c"),  # órfão (regra 8)
        ],
        edges=[
            # Data edge com tipo incompatível (regra 4: code vs string)
            # targetInput 'input' existe em B, mas tipo é 'string' (source é 'code').
            _make_edge(
                "e1",
                "A",
                "B",
                type="data",
                data_mapping=DataMapping(source_output="result", target_input="input"),
            ),
        ],
    )
    result = validate_pipeline(pipeline)
    # Regra 4: tipo incompatível (code vs string)
    r4 = [e for e in result.errors if e.rule == 4]
    assert len(r4) == 1
    # Regra 6: input required não atendido (a data edge mapeia para 'input',
    # mas o tipo é incompatível; a regra 6 verifica se o input é atendido por
    # qualquer data edge, independentemente de tipo)
    # Na verdade, a data edge ATENDE o input 'input' (o nome bate), então
    # regra 6 não dispara. Vamos verificar:
    r6 = [e for e in result.errors if e.rule == 6]
    # A data edge mapeia source_output='result' -> target_input='input'.
    # O input 'input' de B é atendido por esta data edge (o nome bate).
    # Regra 6 não dispara.
    assert len(r6) == 0
    # Regra 8: nós A e C órfãos (A não é entry porque entry_node_id é
    # "NONEXISTENT"; C não tem entrada). B tem entrada (data edge de A).
    r8 = [e for e in result.errors if e.rule == 8]
    assert len(r8) == 2
    orphan_nodes = {e.node_id for e in r8}
    assert orphan_nodes == {"A", "C"}
    # Regra 9: entryNodeId inexistente
    r9 = [e for e in result.errors if e.rule == 9]
    assert len(r9) == 1
    # Não é válido.
    assert not result.is_valid


# ---------------------------------------------------------------------------
# Formato de saída (to_dict)
# ---------------------------------------------------------------------------


def test_result_to_dict_format():
    """to_dict() retorna o formato da spec 4.2."""
    pipeline = Pipeline(
        id="p1",
        name="format-test",
        entry_node_id="NONEXISTENT",
        nodes=[
            _make_node("A", "agent-a"),
        ],
        edges=[],
    )
    result = validate_pipeline(pipeline)
    d = result.to_dict()
    assert "errors" in d
    assert isinstance(d["errors"], list)
    # Cada erro tem rule, message.
    for err in d["errors"]:
        assert "rule" in err
        assert "message" in err
        assert isinstance(err["rule"], int)
        assert isinstance(err["message"], str)


def test_result_to_dict_with_warnings():
    """to_dict() inclui warnings quando existem."""
    pipeline = Pipeline(
        id="p1",
        name="format-warnings",
        entry_node_id="A",
        nodes=[
            _make_node("A", "agent-a", actions=["follow", "return"]),
            _make_node("B", "agent-b"),
        ],
        edges=[
            _make_edge("e1", "A", "B"),
        ],
    )
    result = validate_pipeline(pipeline)
    d = result.to_dict()
    assert "warnings" in d
    assert len(d["warnings"]) == 1
    assert d["warnings"][0]["rule"] == 10
