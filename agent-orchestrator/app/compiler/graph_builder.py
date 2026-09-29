"""Pipeline compiler: JSON da pipeline -> StateGraph do LangGraph.

Função principal: `compile_pipeline(pipeline, *, worker_client, checkpointer=None)`.

Converte o formato de pipeline da spec 4.2 (nodes com agentSnapshot, edges com
type flow/data, source, target) num StateGraph compilado, com:
  - entrada pelo entryNodeId explícito (ADR-010);
  - mapeamento de FlowAction para topologia (follow, return, finalize -> END);
  - fan-out com a semântica de chave versus lista do add_conditional_edges;
  - data edges resolvidas na node function lendo o state do source;
  - data edge sem flow edge injeta flow incondicional (regra 7);
  - requiresApproval gera nó de aprovação approval_node_{edgeId} com interrupt();
  - node function que checa maxIterations, chama o worker_client injetado e
    nunca levanta exceção (ADR-001).

ADR-004: o grafo é recompilado a cada execute/resume. O JSON da pipeline é a
fonte de verdade; o StateGraph não é serializável.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from langgraph.graph import END, START, StateGraph

from app.compiler.state import State
from app.mcp.capability import mint_mcp_capability

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# WorkerClient Protocol (ADR-001: nunca levanta exceção)
# ---------------------------------------------------------------------------


@dataclass
class WorkerResponse:
    """Resposta do worker (contrato HTTP §2.3 do contrato técnico)."""

    status: str  # "completed" | "failed"
    outputs: dict[str, Any] = field(default_factory=dict)
    action: str = "follow"  # "follow" | "return" | "finalize"
    iterations: int = 1
    logs: list[str] = field(default_factory=list)
    error: str | None = None
    # True quando TODAS as tentativas falharam por indisponibilidade do
    # worker (timeout/conexão/5xx) — diferente de "failed" por erro de
    # execução do agente (F14: worker fora do ar -> nó pausa, run retomável;
    # falha do agente -> run failed). ADR-001.
    worker_down: bool = False


class WorkerUnavailableError(Exception):
    """O worker ficou indisponível (F14/ADR-001).

    Levantada pela node function quando TODAS as tentativas do worker_client
    falharam por indisponibilidade (timeout/conexão/5xx). Diferente de uma
    falha de execução do agente (``WorkerResponse(status="failed")``), a
    indisponibilidade NÃO deve encerrar o grafo: o erro propaga para o
    executor, que pausa o run (``pipeline:status = paused``) mantendo o
    checkpoint do nó pendente — a retomada reexecuta o nó (ADR-001: nó falho
    não aborta o grafo; retomada possível).
    """

    def __init__(self, node_id: str, detail: str) -> None:
        super().__init__(f"worker unavailable for node {node_id}: {detail}")
        self.node_id = node_id
        self.detail = detail


@runtime_checkable
class WorkerClient(Protocol):
    """Protocolo do worker client (implementação HTTP: rt-checkpoint).

    A node function injeta esta interface e chama `execute()`.
    A implementação HTTP (app/runtime/worker_client.py) faz retry com backoff
    e NUNCA levanta exceção (ADR-001): qualquer falha vira WorkerResponse
    com status="failed".
    """

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
    ) -> WorkerResponse:
        """Executa o agente no worker. Nunca levanta exceção (ADR-001).

        ``workspace_dir``: workspace do run onde as ferramentas do agente
        trabalham (None = workspace padrão do worker).
        ``mcp_servers``: refs MCP resolvidas no disparo (``[{serverId, tools}]``);
        None = o worker usa as do artefato do agente.
        """
        ...


# ---------------------------------------------------------------------------
# Pipeline dataclasses (formato da spec 4.2, serializável em JSON)
# ---------------------------------------------------------------------------


@dataclass
class PortDef:
    """Definição de port (input ou output) de um agente."""

    name: str
    type: str = "string"
    required: bool = False
    description: str = ""


@dataclass
class AgentSnapshot:
    """Cópia imutável do agente no momento da execução (spec 4.2).

    O compiler usa o agentSnapshot do PipelineNode, não o agente vivo do banco.
    Se o usuário editar o agente durante a execução, a pipeline em andamento
    não é afetada.
    """

    agent_id: str
    version: int = 1
    name: str = ""
    description: str = ""
    prompt: str = ""
    strategy: str = ""
    skills: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    knowledge: list[dict[str, Any]] = field(default_factory=list)
    integrations: list[dict[str, Any]] = field(default_factory=list)
    inputs: list[PortDef] = field(default_factory=list)
    outputs: list[PortDef] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    model: str = ""
    max_iterations: int = 10
    timeout: int = 60
    shell_access: bool = False


@dataclass
class DataMapping:
    """Mapeamento de dados entre source output e target input (spec 4.2)."""

    source_output: str
    target_input: str


@dataclass
class EdgeCondition:
    """Condição estruturada de uma flow edge (spec 4.2).

    V1: apenas field="action". Nunca eval.
    """

    field: str = "action"
    operator: str = "eq"  # "eq" | "neq" | "in" | "not_in"
    value: Any = "follow"  # str | list[str]


@dataclass
class PipelineNode:
    """Nó da pipeline (spec 4.2)."""

    id: str
    agent_id: str
    agent_snapshot: AgentSnapshot
    position: dict[str, float] = field(default_factory=dict)
    label: str | None = None


@dataclass
class PipelineEdge:
    """Aresta da pipeline (spec 4.2)."""

    id: str
    type: str  # "flow" | "data"
    source: str  # nodeId
    target: str  # nodeId
    condition: EdgeCondition | None = None
    label: str | None = None
    requires_approval: bool = False
    approval_channel: str | None = None
    approval_message: str | None = None
    data_mapping: DataMapping | None = None
    reject_target: str | None = None  # ADR-006: target de rejeição


@dataclass
class Pipeline:
    """Pipeline completa (spec 4.2)."""

    id: str
    name: str
    entry_node_id: str
    nodes: list[PipelineNode] = field(default_factory=list)
    edges: list[PipelineEdge] = field(default_factory=list)
    description: str = ""
    status: str = "draft"


# ---------------------------------------------------------------------------
# Helpers de parsing (dict -> dataclass)
# ---------------------------------------------------------------------------


def _parse_port_def(d: dict[str, Any]) -> PortDef:
    return PortDef(
        name=d.get("name", ""),
        type=d.get("type", "string"),
        required=d.get("required", False),
        description=d.get("description", ""),
    )


def _parse_agent_snapshot(d: dict[str, Any]) -> AgentSnapshot:
    return AgentSnapshot(
        agent_id=d.get("agentId", d.get("agent_id", "")),
        version=d.get("version", 1),
        name=d.get("name", ""),
        description=d.get("description", ""),
        prompt=d.get("prompt", ""),
        strategy=d.get("strategy", ""),
        skills=d.get("skills", []),
        tools=d.get("tools", []),
        mcp_servers=d.get("mcpServers", d.get("mcp_servers", [])),
        knowledge=d.get("knowledge", []),
        integrations=d.get("integrations", []),
        inputs=[_parse_port_def(p) for p in d.get("inputs", [])],
        outputs=[_parse_port_def(p) for p in d.get("outputs", [])],
        actions=d.get("actions", []),
        model=d.get("model", ""),
        max_iterations=d.get("maxIterations", d.get("max_iterations", 10)),
        timeout=d.get("timeout", 60),
        shell_access=d.get("shellAccess", d.get("shell_access", False)),
    )


def _parse_edge_condition(d: dict[str, Any]) -> EdgeCondition:
    return EdgeCondition(
        field=d.get("field", "action"),
        operator=d.get("operator", "eq"),
        value=d.get("value", "follow"),
    )


def _parse_data_mapping(d: dict[str, Any]) -> DataMapping:
    return DataMapping(
        source_output=d.get("sourceOutput", d.get("source_output", "")),
        target_input=d.get("targetInput", d.get("target_input", "")),
    )


def _parse_pipeline_node(d: dict[str, Any]) -> PipelineNode:
    snapshot_raw = d.get("agentSnapshot", d.get("agent_snapshot", {}))
    return PipelineNode(
        id=str(d.get("id", "")),
        agent_id=str(d.get("agentId", d.get("agent_id", ""))),
        agent_snapshot=_parse_agent_snapshot(snapshot_raw),
        position=d.get("position", {}),
        label=d.get("label"),
    )


def _parse_pipeline_edge(d: dict[str, Any]) -> PipelineEdge:
    condition_raw = d.get("condition")
    data_mapping_raw = d.get("dataMapping", d.get("data_mapping"))
    return PipelineEdge(
        id=str(d.get("id", "")),
        type=d.get("type", "flow"),
        source=str(d.get("source", "")),
        target=str(d.get("target", "")),
        condition=_parse_edge_condition(condition_raw) if condition_raw else None,
        label=d.get("label"),
        requires_approval=d.get("requiresApproval", d.get("requires_approval", False)),
        approval_channel=d.get("approvalChannel", d.get("approval_channel")),
        approval_message=d.get("approvalMessage", d.get("approval_message")),
        data_mapping=_parse_data_mapping(data_mapping_raw) if data_mapping_raw else None,
        reject_target=d.get("rejectTarget", d.get("reject_target")),
    )


def pipeline_from_dict(d: dict[str, Any]) -> Pipeline:
    """Converte um dict (JSON da spec 4.2) em Pipeline."""
    return Pipeline(
        id=str(d.get("id", "")),
        name=d.get("name", ""),
        entry_node_id=str(d.get("entryNodeId", d.get("entry_node_id", ""))),
        nodes=[_parse_pipeline_node(n) for n in d.get("nodes", [])],
        edges=[_parse_pipeline_edge(e) for e in d.get("edges", [])],
        description=d.get("description", ""),
        status=d.get("status", "draft"),
    )


# ---------------------------------------------------------------------------
# Node function do agente (ADR-001 + ADR-005/007)
# ---------------------------------------------------------------------------


def _make_agent_node(
    node: PipelineNode,
    data_edges_in: list[tuple[str, DataMapping]],
    worker_client: WorkerClient,
    is_entry: bool = False,
    feedback_sources: list[str] | None = None,
    mcp_servers: list[dict[str, Any]] | None = None,
) -> Any:
    """Fábrica do node function de um agente.

    Contrato (D5 Node Function Contract + ADR-001/005/007):
      1. Ler inputs: para cada input do agente, buscar a key no State
         (via dataMapping: qual output de qual nó alimenta este input).
      2. Checar maxIterations NO INÍCIO (ADR-007); se excedido, NÃO roda o
         agente, escreve status="failed" e max_iter_exceeded=True.
      3. Chamar o worker via worker_client (ADR-001, nunca raise).
      4. Escrever outputs em state["data"][nodeId], action em state["actions"],
         status em state["status"], incrementar iterations (soma, ADR-005).
    """
    node_id = node.id
    agent = node.agent_snapshot
    max_iterations = agent.max_iterations
    timeout = agent.timeout

    # Mapeia input name -> (source_node_id, source_output_name)
    input_sources: dict[str, tuple[str, str]] = {}
    for src_node_id, dm in data_edges_in:
        input_sources[dm.target_input] = (src_node_id, dm.source_output)

    async def agent_node(state: State) -> dict[str, Any]:
        # ADR-007: guarda no início. iters = quantas vezes o nó JÁ executou.
        iters = state.get("iterations", {}).get(node_id, 0)
        if iters >= max_iterations:
            return {
                "status": {node_id: "failed"},
                "actions": {node_id: "finalize"},
                "pipeline_status": "failed",
                "max_iter_exceeded": True,
            }

        # 1. Ler inputs: resolver dataMapping lendo o state do source. O nó de
        #    entrada começa com os inputs informados no disparo (run_inputs);
        #    antes eles nunca chegavam ao agente ("Execute your task.").
        inputs: dict[str, Any] = dict(state.get("run_inputs", {}) or {}) if is_entry else {}
        for input_name, (src_node_id, src_output_name) in input_sources.items():
            src_data = state.get("data", {}).get(src_node_id, {})
            if src_output_name in src_data:
                inputs[input_name] = src_data[src_output_name]
        # Argumentar (spec: "agente target retoma com a informação"): o
        # feedback do humano gravado no source da aresta de aprovação.
        for src_node_id in feedback_sources or []:
            feedback = state.get("data", {}).get(src_node_id, {}).get("humanFeedback")
            if feedback:
                inputs["humanFeedback"] = feedback

        # 2. ADR-001/F14: worker indisponível NÃO encerra o grafo.
        #    O worker_client NUNCA levanta exceção (devolve failed); mas a
        #    flag ``worker_down`` (todas as tentativas esgotadas por timeout/
        #    conexão/5xx) vira WorkerUnavailableError para PAUSAR o run no
        #    executor (retomável), em vez de marcar failed e enviar para END.
        #    Falha de execução do agente (status="failed" sem worker_down)
        #    continua encerrando a pipeline (comportamento antigo).
        # Revisão final I4: capacidade MCP do run (o worker só a repassa).
        mcp_kwargs: dict[str, Any] = {}
        if state.get("owner_id"):
            run_id = state.get("run_id") or ""
            mcp_kwargs = {
                "run_id": run_id,
                "mcp_capability": mint_mcp_capability(
                    run_id, state["owner_id"], state.get("workspace_dir") or None
                ),
            }
        try:
            resp = await worker_client.execute(
                agent_id=agent.agent_id,
                node_id=node_id,
                inputs=inputs,
                timeout=timeout,
                workspace_dir=state.get("workspace_dir") or None,
                **({"owner_id": state["owner_id"]} if state.get("owner_id") else {}),
                **mcp_kwargs,
                **({"mcp_servers": mcp_servers} if mcp_servers is not None else {}),
            )
        except Exception as exc:  # noqa: BLE001 — rede de segurança
            logger.exception("worker_client.execute raised unexpectedly for node %s", node_id)
            raise WorkerUnavailableError(node_id, f"unexpected: {exc}") from exc

        if getattr(resp, "worker_down", False):
            logger.warning("worker unavailable; pausing run at node %s", node_id)
            raise WorkerUnavailableError(node_id, resp.error or "unavailable")

        # 3. Escrever outputs namespaceados por nodeId (ADR-003).
        new_data = {node_id: resp.outputs}
        new_status = {node_id: "completed" if resp.status == "completed" else "failed"}
        new_actions = {node_id: resp.action}
        pipeline_status = (
            "failed" if resp.status == "failed" else state.get("pipeline_status", "running")
        )

        # 4. ADR-005: incrementa o contador (soma) a cada execução.
        new_iterations = {node_id: 1}

        update: dict[str, Any] = {
            "data": new_data,
            "status": new_status,
            "actions": new_actions,
            "iterations": new_iterations,
            "pipeline_status": pipeline_status,
            "node_logs": {node_id: list(resp.logs or [])},
        }
        if resp.status == "failed":
            update["node_errors"] = {node_id: resp.error or "falha na execução do agente"}
        return update

    agent_node.__name__ = f"agent_{node_id}"
    return agent_node


# ---------------------------------------------------------------------------
# Nó de aprovação (ADR-006 + ADR-009)
# ---------------------------------------------------------------------------


def _make_approval_node(
    edge: PipelineEdge,
    source_node_id: str,
) -> Any:
    """Fábrica do nó de aprovação (delega para hitl-approval).

    O nó de aprovação é implementado pelo hitl-approval (FASE 7) em
    ``app/approvals/node_function.py``. O compiler (D5) apenas gera a
    topologia e registra a função fornecida pelo D7 no StateGraph.

    Fluxo (spec 5.3 + ADR-006 + ADR-009):
      1. Montar payload (operacional, sem side effects).
      2. interrupt(payload) -> LangGraph pausa e salva checkpoint.
      3. Retomada: interrupt() retorna a resposta.
      4. ADR-009: efeitos colaterais (ApprovalRequest upsert) APÓS o interrupt.
         O executor (D6) faz o upsert; aqui o nó só decide o roteamento.
      5. ADR-006: Command(goto=<id real>) — aprovar -> target, rejeitar ->
         reject_target, argumentar -> feedback no State + target.
    """
    # Import lazy para evitar circular import: node_function importa
    # PipelineEdge de graph_builder, e graph_builder importa create_approval_node
    # de node_function. O import dentro da função quebra o ciclo.
    from app.approvals.node_function import create_approval_node  # noqa: PLC0415

    return create_approval_node(edge, source_node_id)


# ---------------------------------------------------------------------------
# Route function (D5: EdgeCondition -> LangGraph condition)
# ---------------------------------------------------------------------------


def _make_route_fn(
    node_id: str,
    max_iterations: int,
    flow_edges: list[PipelineEdge],
) -> Any:
    """Cria a route_fn de um nó.

    Precedência (ADR-005):
      1. maxIterations excedido -> END
      2. max_iter_exceeded global -> END
      3. Condições das flow edges (field="action", operator, value)
      4. Fallback: "follow" -> primeira flow edge incondicional (ou fan-out)

    A route_fn retorna:
      - str: nome do target (para uma única aresta)
      - list[str]: nomes dos targets (para fan-out)
      - END: para encerrar
    """
    # Separar edges condicionais e incondicionais.
    conditional_edges: list[tuple[EdgeCondition, str]] = []
    unconditional_targets: list[str] = []

    for edge in flow_edges:
        if edge.condition is not None:
            conditional_edges.append((edge.condition, edge.target))
        else:
            unconditional_targets.append(edge.target)

    def route_fn(state: State) -> str | list[str]:
        # ADR-005: maxIterations é checado na node function (não na route_fn).
        # Se a node function detectou maxIterations excedido, ela seta
        # actions[node_id] = "finalize" e max_iter_exceeded = True.
        # A route_fn apenas roteia com base na action.
        action = state.get("actions", {}).get(node_id, "follow")

        # 2. Condições: verificar cada edge condicional.
        for condition, target in conditional_edges:
            if _eval_condition(condition, action):
                return target

        # 3. D5: "finalize" sempre roteia para END (independentemente de
        # haver flow edge explícita). Se nenhuma condição casou e a action
        # é "finalize", o agente quer encerrar a pipeline.
        if action == "finalize":
            return END

        # 4. Fallback: follow -> unconditional targets (fan-out se múltiplos).
        if len(unconditional_targets) == 0:
            # Sem flow edge incondicional: END (segurança).
            return END
        if len(unconditional_targets) == 1:
            return unconditional_targets[0]
        # Fan-out: múltiplos targets em paralelo.
        return unconditional_targets

    return route_fn


def _eval_condition(condition: EdgeCondition, action: str) -> bool:
    """Avalia uma EdgeCondition contra a action do agente.

    V1: apenas field="action". Nunca eval.
    """
    if condition.field != "action":
        # V2: field "status" e "output" (semântica a definir).
        return False

    value = condition.value
    op = condition.operator

    if op == "eq":
        return action == value
    elif op == "neq":
        return action != value
    elif op == "in":
        values = value if isinstance(value, list) else [value]
        return action in values
    elif op == "not_in":
        values = value if isinstance(value, list) else [value]
        return action not in values
    else:
        # Operador desconhecido: não casa.
        return False


# ---------------------------------------------------------------------------
# compile_pipeline: JSON -> StateGraph
# ---------------------------------------------------------------------------


def compile_pipeline(
    pipeline: Pipeline,
    *,
    worker_client: WorkerClient,
    checkpointer: Any = None,
    mcp_servers_by_agent: dict[str, list[dict[str, Any]]] | None = None,
) -> Any:
    """Converte uma Pipeline num StateGraph compilado do LangGraph.

    Puro e determinístico: mesma Pipeline + mesmo worker_client -> mesma topologia.

    Args:
        pipeline: Pipeline com nodes (agentSnapshot) e edges (flow/data).
        worker_client: Implementação do Protocol WorkerClient (injetado).
        checkpointer: Opcional. Se fornecido, o grafo usa este checkpointer
                      (PostgresSaver, MemorySaver, etc.).
        mcp_servers_by_agent: Opcional. agentId -> refs MCP resolvidas pelo
                      executor no disparo; agentes ausentes usam o artefato.

    Returns:
        CompiledStateGraph pronto para ainvoke/astream.

    Regras implementadas:
        - ADR-010: entryNodeId explícito (add_edge(START, entryNodeId)).
        - D5: FlowAction -> topologia (follow, return, finalize -> END).
        - D5: Fan-out (múltiplas flow edges incondicionais do mesmo source).
        - D5: Data edges resolvidas na node function (dataMapping).
        - Regra 7: Data edge sem flow edge injeta flow incondicional.
        - ADR-006: requiresApproval gera nó de aprovação.
        - ADR-001: Node function nunca levanta exceção.
        - ADR-005/007: maxIterations checado na node function.
    """
    graph = StateGraph(State)

    # Separar edges por tipo.
    flow_edges: list[PipelineEdge] = [e for e in pipeline.edges if e.type == "flow"]
    data_edges: list[PipelineEdge] = [e for e in pipeline.edges if e.type == "data"]

    # Regra 7: data edge sem flow edge explícita entre o mesmo par
    # injeta uma flow edge incondicional.
    flow_pairs: set[tuple[str, str]] = {(e.source, e.target) for e in flow_edges}
    injected_flow_edges: list[PipelineEdge] = []
    for de in data_edges:
        pair = (de.source, de.target)
        if pair not in flow_pairs:
            # Injeta flow edge incondicional (regra 7). A aprovação marcada na
            # data edge (o painel oferece o toggle nos dois tipos) vai junto;
            # antes era descartada e o run seguia sem pedir aprovação.
            injected = PipelineEdge(
                id=f"__injected_{de.id}",
                type="flow",
                source=de.source,
                target=de.target,
                condition=None,
                requires_approval=de.requires_approval,
                approval_channel=de.approval_channel,
                approval_message=de.approval_message,
                reject_target=de.reject_target,
            )
            injected_flow_edges.append(injected)
            flow_pairs.add(pair)

    all_flow_edges = flow_edges + injected_flow_edges

    # Mapear data edges por target node: para cada nó, quais data edges entram nele.
    data_edges_by_target: dict[str, list[tuple[str, DataMapping]]] = {}
    for de in data_edges:
        if de.data_mapping is not None:
            data_edges_by_target.setdefault(de.target, []).append((de.source, de.data_mapping))

    # ------------------------------------------------------------------
    # Adicionar nós de agente.
    # ------------------------------------------------------------------
    feedback_sources_by_target: dict[str, list[str]] = {}
    for e in all_flow_edges:
        if e.requires_approval:
            feedback_sources_by_target.setdefault(e.target, []).append(e.source)

    for node in pipeline.nodes:
        data_edges_in = data_edges_by_target.get(node.id, [])
        node_fn = _make_agent_node(
            node,
            data_edges_in,
            worker_client,
            is_entry=node.id == pipeline.entry_node_id,
            feedback_sources=feedback_sources_by_target.get(node.id),
            mcp_servers=(mcp_servers_by_agent or {}).get(node.agent_snapshot.agent_id),
        )
        graph.add_node(node.id, node_fn)

    # ------------------------------------------------------------------
    # Adicionar nós de aprovação (requiresApproval).
    # ------------------------------------------------------------------
    # Para cada flow edge com requiresApproval, inserir um nó de aprovação
    # entre source e target. A edge original é substituída por:
    #   source -> approval_node_{edgeId} -> target (aprovar)
    #   approval_node_{edgeId} -> reject_target (rejeitar)
    # O nó de aprovação decide o destino via Command(goto=<id real>).

    approval_edges: list[PipelineEdge] = []
    non_approval_flow_edges: list[PipelineEdge] = []

    for edge in all_flow_edges:
        if edge.requires_approval:
            approval_edges.append(edge)
        else:
            non_approval_flow_edges.append(edge)

    for edge in approval_edges:
        approval_node_id = f"approval_node_{edge.id}"
        approval_fn = _make_approval_node(edge, edge.source)
        graph.add_node(approval_node_id, approval_fn)
        # source -> approval_node (incondicional).
        # O nó de aprovação decide o destino via Command(goto).
        # Não adicionamos arestas saídas do approval_node: o Command(goto)
        # do nó de aprovação já define o roteamento.
        graph.add_edge(edge.source, approval_node_id)

    # ------------------------------------------------------------------
    # Adicionar arestas condicionais (route_fn) para nós sem aprovação.
    # ------------------------------------------------------------------
    # Para cada nó, coletar as flow edges de saída que NÃO são de aprovação.
    # A route_fn decide para onde ir com base na action no State.

    # Mapear node_id -> flow edges de saída (sem aprovação).
    out_edges_by_node: dict[str, list[PipelineEdge]] = {}
    for edge in non_approval_flow_edges:
        out_edges_by_node.setdefault(edge.source, []).append(edge)

    for node in pipeline.nodes:
        out_edges = out_edges_by_node.get(node.id, [])
        if not out_edges:
            # Nó sem saída: se não é o entry, ele é terminal (vai para END).
            # O LangGraph trata nó sem saída como terminal implicitamente,
            # mas para ser explícito, adicionamos uma conditional edge para END.
            # Na verdade, se o nó não tem edges de saída, ele é terminal.
            # O LangGraph não precisa de aresta explícita para END nesse caso.
            # Mas para o route_fn funcionar, precisamos de uma conditional edge.
            # Solução: se não tem edges, o nó é terminal (END implícito).
            continue

        route_fn = _make_route_fn(
            node.id,
            node.agent_snapshot.max_iterations,
            out_edges,
        )

        # Construir o path_map: mapeia o retorno da route_fn para node ids.
        # A route_fn retorna:
        #   - str: nome do target
        #   - list[str]: nomes dos targets (fan-out)
        #   - END: para encerrar
        # O path_map precisa mapear cada valor possível para o node id.
        # No LangGraph, add_conditional_edges(source, route_fn, path_map)
        # onde path_map mapeia o retorno da route_fn para node ids.
        #
        # Para fan-out, a route_fn retorna uma lista. O LangGraph suporta
        # isso nativamente: se a route_fn retorna uma lista, executa em paralelo.
        #
        # O path_map precisa conter todos os valores possíveis que a route_fn
        # pode retornar. Para "follow" (unconditional), o target é o node id.
        # Para condições, o target é o node id da edge condicional.
        # Para END, o target é END.

        # Coletar todos os targets possíveis.
        path_map: dict[str, str | list[str]] = {}
        for edge in out_edges:
            if edge.condition is not None:
                # Edge condicional: o condition value mapeia para o target.
                # A route_fn retorna o target diretamente (node id).
                path_map[edge.target] = edge.target
            else:
                # Edge incondicional: "follow" mapeia para o target.
                # Se há múltiplas incondicionais (fan-out), a route_fn retorna
                # uma lista. O path_map precisa mapear cada target.
                path_map[edge.target] = edge.target

        # END sempre está no path_map (a route_fn pode retornar END).
        path_map[END] = END

        graph.add_conditional_edges(node.id, route_fn, path_map)

    # ------------------------------------------------------------------
    # ADR-010: entryNodeId explícito.
    # ------------------------------------------------------------------
    graph.add_edge(START, pipeline.entry_node_id)

    # ------------------------------------------------------------------
    # Compilar.
    # ------------------------------------------------------------------
    if checkpointer is not None:
        return graph.compile(checkpointer=checkpointer)
    return graph.compile()
