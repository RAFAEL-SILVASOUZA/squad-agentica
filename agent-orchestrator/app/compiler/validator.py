"""Pipeline graph validator: 11 rules from spec 4.2 + D5 5.2.

Dono: pe-validator (FASE 5). Puro, sem I/O.

Fontes de verdade:
- spec 4.2 "Pipeline (grafo)" — regras 1-11 numeradas.
- D5-pipeline-compiler.md seções 5.1 e 5.2.
- CONTRATO-TECNICO.md ADR-006 (separação flow/data edges).

Formato de erro (spec 4.2):
    {"errors": [{"rule": int, "message": str, "nodeId": str|None, "edgeId": str|None}]}

Regra 10 é AVISO (não erro): actions é capacidade, não obrigação de roteamento.
Regra 7 é TRANSFORMAÇÃO (não erro): data edge sem flow edge injeta flow incondicional.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.compiler.graph_builder import (
    AgentSnapshot,
    Pipeline,
    PipelineEdge,
    PipelineNode,
    PortDef,
)

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ValidationError:
    """Um erro de validação (regra violada)."""

    rule: int
    message: str
    node_id: str | None = None
    edge_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"rule": self.rule, "message": self.message}
        if self.node_id is not None:
            d["nodeId"] = self.node_id
        if self.edge_id is not None:
            d["edgeId"] = self.edge_id
        return d


@dataclass
class ValidationWarning:
    """Um aviso de validação (regra 10: action sem flow edge)."""

    rule: int
    message: str
    node_id: str | None = None
    edge_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"rule": self.rule, "message": self.message}
        if self.node_id is not None:
            d["nodeId"] = self.node_id
        if self.edge_id is not None:
            d["edgeId"] = self.edge_id
        return d


@dataclass
class ValidationResult:
    """Resultado da validação de uma pipeline.

    - errors: lista de erros (regras 1-6, 8, 9, 11). Se não vazia, o grafo é inválido.
    - warnings: lista de avisos (regra 10). Não impedem a persistência.
    - injected_flow_edges: flow edges injetadas pela regra 7 (transformação).
    """

    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationWarning] = field(default_factory=list)
    injected_flow_edges: list[PipelineEdge] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self) -> dict[str, Any]:
        """Formato da spec 4.2: {"errors": [...], "warnings": [...]}."""
        d: dict[str, Any] = {"errors": [e.to_dict() for e in self.errors]}
        if self.warnings:
            d["warnings"] = [w.to_dict() for w in self.warnings]
        return d


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_node(pipeline: Pipeline, node_id: str) -> PipelineNode | None:
    """Busca um nó pelo id."""
    for node in pipeline.nodes:
        if node.id == node_id:
            return node
    return None


def _get_snapshot(pipeline: Pipeline, node_id: str) -> AgentSnapshot | None:
    """Busca o agentSnapshot de um nó."""
    node = _get_node(pipeline, node_id)
    return node.agent_snapshot if node else None


def _find_port(ports: list[PortDef], name: str) -> PortDef | None:
    """Busca um port pelo nome."""
    for port in ports:
        if port.name == name:
            return port
    return None


def _edge_condition_key(edge: PipelineEdge) -> tuple[str, str, str]:
    """Chave de identidade para regra 11: (source, target, condition_repr).

    Duas flow edges são "idênticas" se têm o mesmo source, target e condition.
    Sem condition = incondicional.
    """
    if edge.condition is None:
        cond_repr = "none"
    else:
        cond_repr = f"{edge.condition.field}:{edge.condition.operator}:{str(edge.condition.value)}"
    return (edge.source, edge.target, cond_repr)


# ---------------------------------------------------------------------------
# Regras (cada uma em função própria)
# ---------------------------------------------------------------------------


def _rule_1_data_edge_requires_mapping(pipeline: Pipeline) -> list[ValidationError]:
    """Regra 1: Toda data edge exige dataMapping com sourceOutput e targetInput válidos."""
    errors: list[ValidationError] = []
    for edge in pipeline.edges:
        if edge.type != "data":
            continue
        if edge.data_mapping is None:
            errors.append(
                ValidationError(
                    rule=1,
                    message=f"Data edge '{edge.id}' is missing dataMapping",
                    edge_id=edge.id,
                )
            )
            continue
        if not edge.data_mapping.source_output:
            errors.append(
                ValidationError(
                    rule=1,
                    message=f"Data edge '{edge.id}' has empty sourceOutput in dataMapping",
                    edge_id=edge.id,
                )
            )
        if not edge.data_mapping.target_input:
            errors.append(
                ValidationError(
                    rule=1,
                    message=f"Data edge '{edge.id}' has empty targetInput in dataMapping",
                    edge_id=edge.id,
                )
            )
    return errors


def _rule_2_source_output_exists(pipeline: Pipeline) -> list[ValidationError]:
    """Regra 2: sourceOutput deve existir em outputs do agente source."""
    errors: list[ValidationError] = []
    for edge in pipeline.edges:
        if edge.type != "data" or edge.data_mapping is None:
            continue
        if not edge.data_mapping.source_output:
            continue  # já coberto pela regra 1
        source_snapshot = _get_snapshot(pipeline, edge.source)
        if source_snapshot is None:
            continue  # nó inexistente coberto por outra regra
        port = _find_port(source_snapshot.outputs, edge.data_mapping.source_output)
        if port is None:
            errors.append(
                ValidationError(
                    rule=2,
                    message=(
                        f"Data edge '{edge.id}': sourceOutput '{edge.data_mapping.source_output}' "
                        f"does not exist in outputs of agent '{source_snapshot.agent_id}' "
                        f"(node '{edge.source}')"
                    ),
                    node_id=edge.source,
                    edge_id=edge.id,
                )
            )
    return errors


def _rule_3_target_input_exists(pipeline: Pipeline) -> list[ValidationError]:
    """Regra 3: targetInput deve existir em inputs do agente target."""
    errors: list[ValidationError] = []
    for edge in pipeline.edges:
        if edge.type != "data" or edge.data_mapping is None:
            continue
        if not edge.data_mapping.target_input:
            continue  # já coberto pela regra 1
        target_snapshot = _get_snapshot(pipeline, edge.target)
        if target_snapshot is None:
            continue  # nó inexistente coberto por outra regra
        port = _find_port(target_snapshot.inputs, edge.data_mapping.target_input)
        if port is None:
            errors.append(
                ValidationError(
                    rule=3,
                    message=(
                        f"Data edge '{edge.id}': targetInput '{edge.data_mapping.target_input}' "
                        f"does not exist in inputs of agent '{target_snapshot.agent_id}' "
                        f"(node '{edge.target}')"
                    ),
                    node_id=edge.target,
                    edge_id=edge.id,
                )
            )
    return errors


def _rule_4_port_type_compatible(pipeline: Pipeline) -> list[ValidationError]:
    """Regra 4: Tipo do port compatível entre sourceOutput e targetInput (match exato)."""
    errors: list[ValidationError] = []
    for edge in pipeline.edges:
        if edge.type != "data" or edge.data_mapping is None:
            continue
        if not edge.data_mapping.source_output or not edge.data_mapping.target_input:
            continue  # já coberto pela regra 1
        source_snapshot = _get_snapshot(pipeline, edge.source)
        target_snapshot = _get_snapshot(pipeline, edge.target)
        if source_snapshot is None or target_snapshot is None:
            continue
        src_port = _find_port(source_snapshot.outputs, edge.data_mapping.source_output)
        tgt_port = _find_port(target_snapshot.inputs, edge.data_mapping.target_input)
        if src_port is None or tgt_port is None:
            continue  # já coberto pelas regras 2 e 3
        if src_port.type != tgt_port.type:
            errors.append(
                ValidationError(
                    rule=4,
                    message=(
                        f"Data edge '{edge.id}': type mismatch between sourceOutput "
                        f"'{src_port.name}' (type '{src_port.type}') and targetInput "
                        f"'{tgt_port.name}' (type '{tgt_port.type}')"
                    ),
                    node_id=edge.target,
                    edge_id=edge.id,
                )
            )
    return errors


def _rule_5_different_targets_ok(pipeline: Pipeline) -> list[ValidationError]:
    """Regra 5: Agente pode ter data edge pra B e flow edge pra C (alvos diferentes).

    Esta regra NÃO gera erro. Ela é uma validação de que o padrão é permitido.
    Retorna sempre uma lista vazia (nunca é violação).
    """
    return []


def _rule_6_required_inputs_served(pipeline: Pipeline) -> list[ValidationError]:
    """Regra 6: Target com inputs required sem data edge correspondente → rejeitar.

    Para cada nó target, se o agente tem inputs required, cada um deve ser
    atendido por pelo menos uma data edge (de qualquer origem).
    """
    errors: list[ValidationError] = []
    # Coletar todos os targetInputs atendidos por data edges.
    served_inputs: dict[str, set[str]] = {}  # node_id -> set of input names served
    for edge in pipeline.edges:
        if edge.type == "data" and edge.data_mapping is not None:
            if edge.data_mapping.target_input:
                served_inputs.setdefault(edge.target, set()).add(edge.data_mapping.target_input)

    for node in pipeline.nodes:
        snapshot = node.agent_snapshot
        for port in snapshot.inputs:
            if not port.required:
                continue
            served = served_inputs.get(node.id, set())
            if port.name not in served:
                errors.append(
                    ValidationError(
                        rule=6,
                        message=(
                            f"Node '{node.id}': required input '{port.name}' "
                            f"(type '{port.type}') is not served by any data edge"
                        ),
                        node_id=node.id,
                    )
                )
    return errors


def _rule_7_data_edge_implies_flow(
    pipeline: Pipeline,
) -> tuple[list[ValidationError], list[PipelineEdge]]:
    """Regra 7: Data edge sem flow edge explícita entre o mesmo par → injeta flow edge.

    Esta é uma TRANSFORMAÇÃO, não um erro. Retorna (errors=[], injected_edges).
    Se já existe flow edge explícita entre o mesmo par, a data edge não cria
    uma segunda transição (a flow edge explícita prevalece).
    """
    injected: list[PipelineEdge] = []
    flow_pairs: set[tuple[str, str]] = {
        (e.source, e.target) for e in pipeline.edges if e.type == "flow"
    }
    for de in pipeline.edges:
        if de.type != "data":
            continue
        pair = (de.source, de.target)
        if pair not in flow_pairs:
            # Injeta flow edge incondicional.
            injected.append(
                PipelineEdge(
                    id=f"__injected_{de.id}",
                    type="flow",
                    source=de.source,
                    target=de.target,
                    condition=None,
                    requires_approval=False,
                )
            )
            flow_pairs.add(pair)
    return [], injected


def _rule_8_no_orphan_nodes(pipeline: Pipeline) -> list[ValidationError]:
    """Regra 8: Todo nó (exceto entryNodeId) precisa ter pelo menos uma flow edge
    OU data edge de entrada. Sem isso é nó órfão → rejeitar.

    Nota: a regra 7 injeta flow edges implícitas, então uma data edge de entrada
    também conta como incoming válido.
    """
    errors: list[ValidationError] = []
    # Coletar todos os nodes que têm alguma edge de entrada (flow ou data).
    # Inclui flow edges injetadas pela regra 7 (data edges já cobrem o par).
    incoming_nodes: set[str] = set()
    for edge in pipeline.edges:
        # Tanto flow quanto data edges agendam execução no target.
        incoming_nodes.add(edge.target)

    for node in pipeline.nodes:
        if node.id == pipeline.entry_node_id:
            continue  # entry node não precisa de entrada
        if node.id not in incoming_nodes:
            errors.append(
                ValidationError(
                    rule=8,
                    message=(
                        f"Node '{node.id}' is orphan: no incoming flow or data edge "
                        f"(and it is not the entry node)"
                    ),
                    node_id=node.id,
                )
            )
    return errors


def _rule_9_entry_node_exists(pipeline: Pipeline) -> list[ValidationError]:
    """Regra 9: entryNodeId deve referenciar um nó existente em nodes."""
    errors: list[ValidationError] = []
    if not pipeline.entry_node_id:
        errors.append(
            ValidationError(
                rule=9,
                message="Pipeline has no entryNodeId set",
            )
        )
        return errors
    node = _get_node(pipeline, pipeline.entry_node_id)
    if node is None:
        errors.append(
            ValidationError(
                rule=9,
                message=(
                    f"entryNodeId '{pipeline.entry_node_id}' does not reference "
                    f"an existing node in the pipeline"
                ),
            )
        )
    return errors


def _rule_10_action_without_flow_edge(pipeline: Pipeline) -> list[ValidationWarning]:
    """Regra 10: Se um agente declara uma action mas nenhuma flow edge com essa
    condition sai dele → AVISO (não erro).

    O grafo é válido: actions é o que o agente PODE produzir, não o que
    o grafo DEVE rotear.
    """
    warnings: list[ValidationWarning] = []
    for node in pipeline.nodes:
        snapshot = node.agent_snapshot
        if not snapshot.actions:
            continue
        # Coletar as conditions das flow edges que saem deste nó.
        outgoing_flow_edges = [
            e for e in pipeline.edges if e.type == "flow" and e.source == node.id
        ]
        # Para cada action declarada, verificar se há uma flow edge condicional
        # que a roteia. "follow" é o fallback (sempre roteado), "finalize" vai
        # para END (sempre roteado). Apenas actions como "return" precisam de
        # flow edge condicional explícita.
        for action in snapshot.actions:
            if action in ("follow", "finalize"):
                # follow: roteado pelo fallback incondicional.
                # finalize: roteado para END pelo compiler (D5).
                continue
            # Verificar se alguma flow edge condicional deste nó casa com a action.
            has_edge = False
            for edge in outgoing_flow_edges:
                if edge.condition is not None and edge.condition.field == "action":
                    val = edge.condition.value
                    if edge.condition.operator == "eq" and val == action:
                        has_edge = True
                        break
                    elif (
                        edge.condition.operator == "in"
                        and isinstance(val, list)
                        and action in val
                    ):
                        has_edge = True
                        break
            if not has_edge:
                warnings.append(
                    ValidationWarning(
                        rule=10,
                        message=(
                            f"Node '{node.id}': agent declares action '{action}' but no "
                            f"flow edge with that condition exits this node. "
                            f"The action will not be routed (warning only)."
                        ),
                        node_id=node.id,
                    )
                )
    return warnings


def _rule_11_no_duplicate_flow_edges(pipeline: Pipeline) -> list[ValidationError]:
    """Regra 11: Múltiplas flow edges entre o mesmo par com conditions diferentes
    são permitidas (branching). Duas flow edges idênticas (mesma condition)
    entre o mesmo par → rejeitar (redundante).
    """
    errors: list[ValidationError] = []
    seen: dict[tuple[str, str, str], str] = {}  # key -> first edge id
    for edge in pipeline.edges:
        if edge.type != "flow":
            continue
        key = _edge_condition_key(edge)
        if key in seen:
            errors.append(
                ValidationError(
                    rule=11,
                    message=(
                        f"Duplicate flow edge '{edge.id}' between '{edge.source}' and "
                        f"'{edge.target}' with the same condition as edge '{seen[key]}'"
                    ),
                    edge_id=edge.id,
                )
            )
        else:
            seen[key] = edge.id
    return errors


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def validate_pipeline(pipeline: Pipeline) -> ValidationResult:
    """Valida uma pipeline contra as 11 regras da spec 4.2 + D5 5.2.

    Puro, sem I/O. Não modifica a pipeline.

    Args:
        pipeline: Pipeline com nodes (agentSnapshot) e edges (flow/data).

    Returns:
        ValidationResult com errors (regras violadas), warnings (regra 10)
        e injected_flow_edges (regra 7: transformação).

    Regras:
        1. Data edge exige dataMapping com sourceOutput e targetInput válidos.
        2. sourceOutput existe em outputs do agente source.
        3. targetInput existe em inputs do agente target.
        4. Tipo do port compatível (match exato de string).
        5. Agente pode ter data edge pra B e flow edge pra C (não é erro).
        6. Target com inputs required sem data edge → rejeitar.
        7. Data edge sem flow edge → injeta flow incondicional (transformação).
        8. Todo nó (exceto entry) tem flow edge OU data edge de entrada.
        9. entryNodeId referencia um nó existente.
        10. Action sem flow edge condicional → aviso (não erro).
        11. Duas flow edges idênticas entre o mesmo par → rejeitar.
    """
    result = ValidationResult()

    # Regras que geram erros.
    result.errors.extend(_rule_1_data_edge_requires_mapping(pipeline))
    result.errors.extend(_rule_2_source_output_exists(pipeline))
    result.errors.extend(_rule_3_target_input_exists(pipeline))
    result.errors.extend(_rule_4_port_type_compatible(pipeline))
    # Regra 5: nunca gera erro (padrão permitido).
    result.errors.extend(_rule_5_different_targets_ok(pipeline))
    result.errors.extend(_rule_6_required_inputs_served(pipeline))
    # Regra 7: transformação (injeta flow edges).
    _, injected = _rule_7_data_edge_implies_flow(pipeline)
    result.injected_flow_edges = injected
    result.errors.extend(_rule_8_no_orphan_nodes(pipeline))
    result.errors.extend(_rule_9_entry_node_exists(pipeline))
    # Regra 10: avisos.
    result.warnings.extend(_rule_10_action_without_flow_edge(pipeline))
    # Regra 11: erros.
    result.errors.extend(_rule_11_no_duplicate_flow_edges(pipeline))

    return result
