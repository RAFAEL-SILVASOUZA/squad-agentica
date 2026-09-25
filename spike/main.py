"""Spike LangGraph — prova de arquitetura da orquestração.

Pipeline A -> [aprovação] -> B com loop-back por rejeição e maxIterations.

Autocontido: NÃO importa nada de agent-orchestrator/. Só prova o padrão de
orquestração do contrato técnico (ADR-001..ADR-011), sem LLM, sem MinIO, sem auth.

Padrões provados (cada um está marcado com o comentário # ADR-XXX):
  - ADR-001: node function nunca levanta exceção do worker; erro vira state update.
  - ADR-002: State schema FIXO (TypedDict com keys fixas + reducers Annotated).
  - ADR-003: namespace por nodeId é convenção de valor dentro de `data`.
  - ADR-004: resume recompila o grafo do JSON (compile_pipeline + compile_and_resume).
  - ADR-005/007: maxIterations checado no início da node function; iterations = soma.
  - ADR-006: Command(goto=<id real de nó>); rejectTarget configurável (edge.rejectTarget).
  - ADR-009: ApprovalRequest (mock) upsert pós-interrupt, idempotente por chave.

API real confirmada (langgraph 0.2.61 / langgraph-checkpoint-postgres 2.0.10):
  - interrupt(value) é primitivo de nó; Command(goto=..., resume=..., update=...).
  - PostgresSaver(conn) toma uma connection/pool psycopg; setup() cria as tabelas.
  - astream(input, config) gera o estado; NÃO há stream.interrupted (ver README).
  - get_state(config) -> StateSnapshot(values, next, config, metadata, tasks).
"""

from __future__ import annotations

import asyncio
import json
import operator
from typing import Annotated, Any, Callable, Optional, TypedDict

import httpx
from langgraph.checkpoint.base import Checkpoint, CheckpointTuple, CheckpointMetadata
from langgraph.checkpoint.postgres import PostgresSaver as SyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, RunnableConfig, interrupt
from pydantic import BaseModel


def _merge_dicts(acc: dict, val: dict) -> dict:
    """Reducer de merge (overwrite por chave) para dicts indexados por nodeId.

    Usado em `data`, `actions`, `status`: cada nó escreve só a sua chave
    (`state["data"][nodeId]`), então o merge por chave não perde dados de outros
    nós. LangGraph não tem reducer nativo de merge de dicts (o default é
    `last`/overwrite, que perderia as chaves dos outros nós).
    """
    if not val:
        return acc
    out = dict(acc)
    out.update(val)
    return out


def _sum_dicts(acc: dict, val: dict) -> dict:
    """Reducer de SOMA para dicts indexados por nodeId (ADR-005).

    Usado em `iterations`: cada execução soma 1 ao contador do seu nodeId; nós
    diferentes não colidem. O contrato pede `Annotated[int, operator.add]` para
    `iterations`, mas o schema fixo (ADR-002) tem `iterations` como dict por nodeId,
    então o reducer de soma é aplicado por chave (equivalente, e JSON-serializável).
    """
    if not val:
        return acc
    out = dict(acc)
    for k, v in val.items():
        out[k] = out.get(k, 0) + v
    return out

# ---------------------------------------------------------------------------
# Configuração (env). O spike usa o mesmo Postgres isolado do docker-compose.
# ---------------------------------------------------------------------------
DATABASE_URL = "postgresql://spike:spike@localhost:15433/spike"
WORKER_URL = "http://localhost:9100"
WORKER_TIMEOUT = float(__import__("os").environ.get("SPIKE_WORKER_TIMEOUT", "5"))
WORKER_MAX_RETRIES = int(__import__("os").environ.get("SPIKE_WORKER_MAX_RETRIES", "3"))

# ---------------------------------------------------------------------------
# ADR-002: State schema FIXO. Nunca TypedDict dinâmico (quebra no checkpoint
# round-trip). Reducers explícitos: `iterations` = soma, `max_iter_exceeded` = or.
# ---------------------------------------------------------------------------
State = TypedDict(
    "State",
    {
        # ADR-003: os valores são dicts indexados por nodeId (convenção de valor).
        # Reducer de merge por chave: cada nó escreve só a sua chave.
        "data": Annotated[dict, _merge_dicts],
        # {nodeId: "follow"|"return"|"finalize"} — ação para roteamento.
        "actions": Annotated[dict, _merge_dicts],
        # {nodeId: "completed"|"failed"|"interrupted"} — status do nó.
        "status": Annotated[dict, _merge_dicts],
        # {nodeId: int} — contador por nó, reducer de SOMA (ADR-005). Cada execução
        # soma 1 ao contador do seu nodeId; nós diferentes não colidem.
        "iterations": Annotated[dict, _sum_dicts],
        # bool global: true se algum nó excedeu maxIterations (ADR-005).
        "max_iter_exceeded": Annotated[bool, operator.or_],
        # "running"|"completed"|"failed" — status da pipeline.
        "pipeline_status": str,
    },
)

# ADR-006: rejectTarget padrão = loop-back para o source (o próprio nó de aprovação
# aponta de volta pro source). Configuração da aresta, nunca string hardcoded.
REJECT_TARGET_DEFAULT = "loop_back"


class PostgresSaver(SyncPostgresSaver):
    """PostgresSaver com suporte a operações assíncronas.

    Surpresa da API real (langgraph-checkpoint-postgres 2.0.10): a classe
    `PostgresSaver` (síncrona) implementa SÓ os métodos síncronos
    (`get_tuple`, `put`, `list`, `put_writes`). Os métodos assíncronos
    (`aget_tuple`, `aput`, ...) herdam stubs de `BaseCheckpointSaver` que
    levantam `NotImplementedError`. Como os nós do grafo são assíncronos
    (httpx), o `astream` precisa de um checkpointer síncrono-bridge.

    Aqui fazemos o bridge: os métodos async delegam para os síncronos em
    `asyncio.to_thread`. A conexão é reutilizável (psycopg 3 com autocommit).
    """

    async def aget_tuple(
        self, config: Optional[RunnableConfig]
    ) -> Optional[CheckpointTuple]:
        return await asyncio.to_thread(self.get_tuple, config)

    async def aget(self, config: Optional[RunnableConfig]) -> Optional[Checkpoint]:
        return await asyncio.to_thread(self.get, config)

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: Any,
    ) -> RunnableConfig:
        return await asyncio.to_thread(
            self.put, config, checkpoint, metadata, new_versions
        )

    async def aput_writes(
        self, config: RunnableConfig, writes: Any, task_id: str
    ) -> None:
        await asyncio.to_thread(self.put_writes, config, writes, task_id)

    async def alist(self, config: Optional[RunnableConfig], **kwargs: Any) -> Any:
        # `list` é um generator síncrono; converte para async iterator.
        result = list(self.list(config, **kwargs))
        for item in result:
            yield item


# ---------------------------------------------------------------------------
# Worker client (ADR-001: retry + timeout, nunca propaga exceção).
# ---------------------------------------------------------------------------
class WorkerResponse(BaseModel):
    status: str
    outputs: dict[str, Any]
    action: str
    iterations: int
    logs: list[str]
    error: str | None = None


async def worker_execute(
    agent_id: str,
    inputs: dict[str, Any],
    *,
    timeout: float = WORKER_TIMEOUT,
    max_retries: int = WORKER_MAX_RETRIES,
    fail: bool = False,
    delay: float = 0.0,
) -> WorkerResponse:
    """Chama o worker via httpx async com timeout e retry.

    Nunca levanta exceção: qualquer falha de rede/timeout vira um WorkerResponse
    com status="failed" e error preenchido (ADR-001). O node function consome isso
    e escreve {"status":"failed","error":...} no State; o grafo NÃO aborta.
    """
    payload = {
        "agentId": agent_id,
        "nodeId": agent_id,
        "inputs": inputs,
        "timeout": int(timeout),
        "fail": fail,
        "delay": delay,
    }
    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(f"{WORKER_URL}/execute", json=payload)
            if resp.status_code == 401:
                raise RuntimeError("worker token inválido")
            resp.raise_for_status()
            data = resp.json()
            return WorkerResponse(**data)
        except (httpx.HTTPError, RuntimeError, json.JSONDecodeError) as exc:
            last_err = exc
            if attempt < max_retries:
                await asyncio.sleep(2 ** (attempt - 1))  # backoff 2s,4s,...
    # Todas as tentativas falharam: devolve failed, nunca raise (ADR-001).
    return WorkerResponse(
        status="failed",
        outputs={},
        action="follow",
        iterations=0,
        logs=[f"[{agent_id}] worker unreachable after {max_retries} retries: {last_err}"],
        error=f"worker unreachable: {last_err}",
    )


# ---------------------------------------------------------------------------
# Node function do agente (ADR-001 + ADR-005/007).
# ---------------------------------------------------------------------------
def make_agent_node(
    node_id: str,
    agent_id: str,
    max_iterations: int,
    *,
    fail: bool = False,
    delay: float = 0.0,
) -> Callable:
    """Fábrica do node function de um agente.

    Contrato (D5 Node Function Contract + ADR-005/007):
      1. ler inputs de `state["data"][node_id]`;
      2. checar maxIterations NO INÍCIO (ADR-007); se excedido, NÃO roda o agente,
         escreve status="failed" e deixa a route_fn decidir (END);
      3. chamar o worker via httpx (ADR-001, nunca raise);
      4. escrever outputs em `state["data"][node_id]`, action em `state["actions"]`,
         status em `state["status"]`, incrementar `iterations` (soma, ADR-005).
    """

    async def agent_node(state: State) -> dict[str, Any]:
        # ADR-007: guarda no início. iters = quantas vezes o nó JÁ executou (o reducer
        # de soma acumulou 1 por execução). Se já excedeu, não roda o agente.
        iters = state.get("iterations", {}).get(node_id, 0)
        if iters >= max_iterations:
            return {
                "status": {node_id: "failed"},
                "actions": {node_id: "finalize"},
                "pipeline_status": "failed",
                "max_iter_exceeded": True,
            }

        inputs = state.get("data", {}).get(node_id, {})

        # ADR-001: worker nunca levanta exceção.
        resp = await worker_execute(
            agent_id,
            inputs,
            timeout=WORKER_TIMEOUT,
            fail=fail,
            delay=delay,
        )

        # Escreve o output do agente namespaceado por nodeId (ADR-003).
        new_data = {node_id: resp.outputs}
        new_status = {node_id: "completed" if resp.status == "completed" else "failed"}
        new_actions = {node_id: resp.action}
        pipeline_status = "failed" if resp.status == "failed" else state.get(
            "pipeline_status", "running"
        )

        # ADR-005: incrementa o contador (soma) a cada execução, independentemente do
        # status do worker. Assim o loop de rejeição (loop-back) é cortado por
        # maxIterations mesmo quando o worker falha.
        new_iterations = {node_id: 1}

        return {
            "data": new_data,
            "status": new_status,
            "actions": new_actions,
            "iterations": new_iterations,
            "pipeline_status": pipeline_status,
        }

    agent_node.__name__ = f"agent_{node_id}"
    return agent_node


# ---------------------------------------------------------------------------
# ADR-009: ApprovalRequest mock (upsert idempotente por chave).
# ---------------------------------------------------------------------------
class ApprovalStore:
    """Store mock de ApprovalRequest. Idempotente por chave (runId, nodeId, interruptId)."""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str, str], dict[str, Any]] = {}

    def upsert(self, run_id: str, node_id: str, interrupt_id: str, message: str) -> dict[str, Any]:
        key = (run_id, node_id, interrupt_id)
        existing = self._rows.get(key)
        if existing is None:
            row = {
                "approvalId": f"{run_id}-{node_id}",
                "runId": run_id,
                "nodeId": node_id,
                "interruptId": interrupt_id,
                "message": message,
                "status": "pending",
                "created": True,
            }
            self._rows[key] = row
            return row
        return {**existing, "created": False}


approval_store = ApprovalStore()


# ---------------------------------------------------------------------------
# ADR-006: nó de aprovação com interrupt() + Command(goto=<id real>).
# ---------------------------------------------------------------------------
def make_approval_node(
    node_id: str,
    edge_id: str,
    approve_target: str,
    reject_target: str,
    *,
    message: str = "Aprovação necessária",
) -> Callable:
    """Fábrica do nó de aprovação.

    Fluxo (D7 §7.1):
      1. montar payload (operacional, sem side effects);
      2. interrupt(payload) -> LangGraph pausa e salva checkpoint;
      3. retomada: interrupt() retorna a resposta;
      4. persistir ApprovalRequest (upsert pós-interrupt, ADR-009);
      5. Command(goto=<id real>) — aprovar -> approve_target, rejeitar -> reject_target.
    """

    async def approval_node(state: State, config: dict[str, Any]) -> dict[str, Any]:
        run_id = config.get("configurable", {}).get("run_id", "run")
        # interrupt_id real do LangGraph: o task id da pausa (UUID). Estável entre
        # execuções/resumes da mesma pausa, então serve de chave de idempotência
        # (ADR-009). O task id vem do config interno do LangGraph (CONFIG_KEY_TASK_ID).
        from langgraph.constants import CONFIG_KEY_TASK_ID

        interrupt_id = config.get("configurable", {}).get(CONFIG_KEY_TASK_ID, "int-0")

        # ADR-009: persistência e notificação APÓS o interrupt(), com upsert idempotente
        # por chave (runId, nodeId, interruptId). Re-execuções não duplicam.
        decision = interrupt({"message": message, "approvalId": f"{run_id}-{node_id}"})
        approval_store.upsert(run_id, node_id, interrupt_id, message)

        # ADR-006: goto só com IDs reais de nó. rejectTarget vem da configuração da aresta.
        if decision == "approved":
            return Command(goto=approve_target)
        # rejeitar -> reject_target (loop-back pro source por padrão, ou END se configurado)
        return Command(goto=reject_target)

    approval_node.__name__ = f"approval_{edge_id}"
    return approval_node


# ---------------------------------------------------------------------------
# ADR-005/007: route_fn por nó. Precedência: maxIterations -> END, depois action.
# ---------------------------------------------------------------------------
def make_route_fn(node_id: str, max_iterations: int) -> Callable:
    """route_fn que decide para onde ir com base na ação no State.

    Precedência (ADR-005): se maxIterations excedido -> END; senão, segue a ação
    (follow -> próximo, return -> loop, finalize -> END).
    """

    def route_fn(state: State) -> str:
        iters = state.get("iterations", {}).get(node_id, 0)
        if iters >= max_iterations or state.get("max_iter_exceeded"):
            return END
        action = state.get("actions", {}).get(node_id, "follow")
        return action  # "follow"|"return"|"finalize"

    return route_fn


# ---------------------------------------------------------------------------
# ADR-004: compiler. JSON da pipeline -> StateGraph. Recompila sempre.
# ---------------------------------------------------------------------------
class PipelineJSON(BaseModel):
    """JSON mínimo da pipeline que o compiler consome (ADR-004)."""

    entry_node_id: str
    nodes: dict[str, dict[str, Any]]
    # edges: {edge_id: {source, target, requires_approval, approve_target, reject_target}}
    edges: dict[str, dict[str, Any]]


def compile_pipeline(pipeline: PipelineJSON) -> StateGraph:
    """Converte o JSON da pipeline num StateGraph (ADR-004: recompila sempre)."""
    graph = StateGraph(State)

    # Nós de agente.
    for node_id, cfg in pipeline.nodes.items():
        if cfg.get("is_approval"):
            continue  # nós de aprovação são gerados a partir das edges
        graph.add_node(
            node_id,
            make_agent_node(
                node_id,
                cfg["agent_id"],
                cfg.get("max_iterations", 10),
                fail=cfg.get("fail", False),
                delay=cfg.get("delay", 0.0),
            ),
        )

    # ADR-006: arestas. source -> approval_node -> target (aprovar) / reject_target (rejeitar).
    for edge_id, edge in pipeline.edges.items():
        source = edge["source"]
        if edge.get("requires_approval"):
            approve_target = edge.get("approve_target", edge["target"])
            reject_target = edge.get("reject_target", REJECT_TARGET_DEFAULT)
            if reject_target == REJECT_TARGET_DEFAULT:
                reject_target = source  # loop-back pro source por padrão
            approval_node_id = f"approval_{edge_id}"
            graph.add_node(
                approval_node_id,
                make_approval_node(
                    approval_node_id,
                    edge_id,
                    approve_target,
                    reject_target,
                    message=edge.get("message", "Aprovação necessária"),
                ),
            )
            # source -> approval_node (incondicional). O nó de aprovação decide o destino
            # via Command(goto=<id real>) retornado (ADR-006): aprovar -> target,
            # rejeitar -> reject_target. Sem conditional edges redundantes.
            graph.add_edge(source, approval_node_id)
        else:
            graph.add_edge(source, edge["target"])

    # ADR-010: entryNodeId explícito.
    graph.add_edge(START, pipeline.entry_node_id)
    return graph


# ---------------------------------------------------------------------------
# ADR-004: compile_and_resume. Recompila o grafo do JSON e invoca.
# ---------------------------------------------------------------------------
async def compile_and_resume(
    pipeline_json: dict[str, Any],
    saver: PostgresSaver,
    config: dict[str, Any],
    resume_value: Any,
) -> dict[str, Any]:
    """Recompila o grafo do JSON e chama ainvoke(Command(resume=...)) (ADR-004).

    Surpresa da API real (langgraph 0.2.61): `ainvoke` devolve só o update do
    ÚLTIMO superstep (delta), não o estado completo. Para o estado completo, usa
    `get_state(config).values` após o resume. O resume retoma do ponto de
    interrupção (não recomeça do START) porque o checkpointer carrega o
    checkpoint_id da pausa pela thread_id.
    """
    graph = compile_pipeline(PipelineJSON(**pipeline_json)).compile(checkpointer=saver)

    # Para retomar do ponto de interrupção (não recomeçar do início), usamos a
    # config do snapshot atual da thread, que carrega o checkpoint_id da pausa.
    snap = graph.get_state(config)
    resume_config = snap.config if snap is not None else config

    # Os nós são assíncronos (httpx), então usa ainvoke, não invoke.
    await graph.ainvoke(Command(resume=resume_value), config=resume_config)

    # Estado completo pós-resume (não o delta do último superstep).
    final_snap = graph.get_state(config)
    return dict(final_snap.values) if final_snap is not None else {}


# ---------------------------------------------------------------------------
# ADR-001/ADR-005: executor com streaming. Nunca propaga exceção do grafo.
# ---------------------------------------------------------------------------
async def run_pipeline(
    pipeline_json: dict[str, Any],
    saver: PostgresSaver,
    config: dict[str, Any],
    initial_state: dict[str, Any],
    *,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Executa a pipeline com astream, detectando interrupção e falha de nó.

    Streaming com a API do contrato: astream gera o estado por superstep. A
    interrupção é detectada pelo StateSnapshot retornado por get_state (tasks com
    interrupts) — NÃO há stream.interrupted (ver README sobre divergência).
    """
    graph = compile_pipeline(PipelineJSON(**pipeline_json)).compile(checkpointer=saver)

    interrupted = False
    interrupt_info: Any = None
    # Usa stream_mode="updates": o interrupt aparece como update
    # {"__interrupt__": (Interrupt(...),)} — a forma mais confiável de detectar
    # pausa (NÃO há stream.interrupted; ver README sobre divergência).
    async for update in graph.astream(
        initial_state, config=config, stream_mode="updates"
    ):
        if "__interrupt__" in update:
            interrupted = True
            interrupt_info = update["__interrupt__"]
            if on_event:
                on_event({"type": "interrupted", "interrupt": interrupt_info})
            break
        if on_event:
            on_event({"type": "state", "node": list(update.keys())})

    # Estado completo via get_state (não o delta do stream). O snapshot traz
    # values (estado completo), next (próximos nós) e tasks (com interrupts).
    snap = graph.get_state(config)
    final_state = dict(snap.values) if snap is not None else {}

    if not interrupted:
        if on_event:
            on_event({"type": "done", "state": final_state})

    return {"state": final_state, "interrupted": interrupted, "interrupt": interrupt_info}


# ---------------------------------------------------------------------------
# Ponto de entrada para execução manual (python main.py).
# ---------------------------------------------------------------------------
async def _demo() -> None:
    import os

    from psycopg import connect

    conn = connect(DATABASE_URL, autocommit=True)
    saver = PostgresSaver(conn)
    saver.setup()

    pipeline_json = {
        "entry_node_id": "agent_a",
        "nodes": {
            "agent_a": {"agent_id": "agent-a", "max_iterations": 3},
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

    config = {
        "configurable": {
            "thread_id": "spike-demo",
            "run_id": "run-demo",
            "interrupt_id": "int-0",
        }
    }
    initial_state = {
        "data": {"agent_a": {"prompt": "hello"}, "agent_b": {}},
        "iterations": {},
        "status": {},
        "actions": {},
        "max_iter_exceeded": False,
        "pipeline_status": "running",
    }

    print("=== executando pipeline A -> [aprovação] -> B ===")
    result = await run_pipeline(pipeline_json, saver, config, initial_state)
    print("interrupted:", result["interrupted"])
    print("final state:", json.dumps(result["state"], indent=2, default=str))
    print("para retomar, chame compile_and_resume(...) com Command(resume='approved')")
    conn.close()


if __name__ == "__main__":
    asyncio.run(_demo())
