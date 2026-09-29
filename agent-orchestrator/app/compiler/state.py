"""State schema FIXO do pipeline (ADR-002 do contrato técnico).

Nunca TypedDict dinâmico: o schema é estável e sobrevive a recompilações
(ADR-004) e ao checkpoint round-trip no PostgresSaver.

ADR-003: o namespace por nodeId é convenção de valor dentro dos dicts,
não feature de schema. Os valores de `data`, `actions`, `status` e
`iterations` são dicts indexados por nodeId.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def _merge_dicts(acc: dict[str, Any], val: dict[str, Any]) -> dict[str, Any]:
    """Reducer de merge (overwrite por chave) para dicts indexados por nodeId.

    Usado em `data`, `actions`, `status`: cada nó escreve só a sua chave
    (`state["data"][nodeId]`), então o merge por chave não perde dados de
    outros nós. LangGraph não tem reducer nativo de merge de dicts (o default
    é `last`/overwrite, que perderia as chaves dos outros nós).
    """
    if not val:
        return acc
    out = dict(acc)
    out.update(val)
    return out


def _sum_dicts(acc: dict[str, Any], val: dict[str, Any]) -> dict[str, Any]:
    """Reducer de SOMA para dicts indexados por nodeId (ADR-005).

    Usado em `iterations`: cada execução soma 1 ao contador do seu nodeId;
    nós diferentes não colidem. O contrato pede `Annotated[int, operator.add]`
    para `iterations`, mas o schema fixo (ADR-002) tem `iterations` como dict
    por nodeId, então o reducer de soma é aplicado por chave (equivalente, e
    JSON-serializável).
    """
    if not val:
        return acc
    out = dict(acc)
    for k, v in val.items():
        out[k] = out.get(k, 0) + v
    return out


# Precedência de status: failed > running > completed.
# Em fan-out, dois nós podem escrever pipeline_status no mesmo superstep.
# O reducer escolhe o "pior" status (failed tem precedência).
_STATUS_PRIORITY = {"failed": 2, "running": 1, "completed": 0}


def _pipeline_status_reducer(acc: str, val: str) -> str:
    """Reducer para pipeline_status: escolhe o status com maior precedência.

    Em fan-out, múltiplos nós escrevem pipeline_status no mesmo superstep.
    O reducer resolve o conflito escolhendo o "pior" status:
    failed > running > completed.
    """
    if acc == val:
        return acc
    if _STATUS_PRIORITY.get(acc, 0) >= _STATUS_PRIORITY.get(val, 0):
        return acc
    return val


class State(TypedDict):
    """State schema fixo do pipeline (ADR-002).

    Keys:
        data: ports namespaced por nodeId. Cada nó escreve em
              `data[nodeId]` um dict com os outputs do agente.
              Reducer: merge por chave (overwrite).
        actions: {nodeId: "follow"|"return"|"finalize"} — ação para roteamento.
                 Reducer: merge por chave.
        status: {nodeId: "completed"|"failed"|"interrupted"} — status do nó.
                Reducer: merge por chave.
        iterations: {nodeId: int} — contador por nó.
                    Reducer: SOMA por chave (ADR-005).
        max_iter_exceeded: bool global — true se algum nó excedeu maxIterations.
                           Reducer: or_.
        pipeline_status: "running"|"completed"|"failed" — status da pipeline.
                         Reducer: last (default LangGraph).
    """

    # ADR-003: os valores são dicts indexados por nodeId (convenção de valor).
    # Reducer de merge por chave: cada nó escreve só a sua chave.
    data: Annotated[dict[str, Any], _merge_dicts]
    # {nodeId: "follow"|"return"|"finalize"} — ação para roteamento.
    actions: Annotated[dict[str, str], _merge_dicts]
    # {nodeId: "completed"|"failed"|"interrupted"} — status do nó.
    status: Annotated[dict[str, str], _merge_dicts]
    # {nodeId: int} — contador por nó, reducer de SOMA (ADR-005). Cada execução
    # soma 1 ao contador do seu nodeId; nós diferentes não colidem.
    iterations: Annotated[dict[str, int], _sum_dicts]
    # bool global: true se algum nó excedeu maxIterations (ADR-005).
    max_iter_exceeded: Annotated[bool, operator.or_]
    # "running"|"completed"|"failed" — status da pipeline.
    # Reducer: precedência (failed > running > completed) para fan-out.
    pipeline_status: Annotated[str, _pipeline_status_reducer]
    # {nodeId: [linhas]} e {nodeId: mensagem} — logs e erro devolvidos pelo
    # worker, publicados pelo executor como ``pipeline:log`` (contrato §7).
    # {inputName: valor} informados no disparo da execução; lidos pelo nó de
    # entrada (os demais recebem dados por data edge).
    run_inputs: Annotated[dict[str, Any], _merge_dicts]
    node_logs: Annotated[dict[str, list[str]], _merge_dicts]
    node_errors: Annotated[dict[str, str], _merge_dicts]
    # Diretório do workspace do run (volume compartilhado com o worker); ""
    # quando o run não tem workspace. Reducer: last (default LangGraph).
    workspace_dir: str
    owner_id: str
    # Id do PipelineRun (capacidade MCP por run, revisão final I4).
    run_id: str


def initial_state() -> dict[str, Any]:
    """Estado inicial para uma nova execução de pipeline.

    Todos os dicts vazios, iterations em 0, pipeline_status em "running".
    O executor (D6) preenche `data[entryNodeId]` com os inputs iniciais.
    """
    return {
        "data": {},
        "actions": {},
        "status": {},
        "iterations": {},
        "max_iter_exceeded": False,
        "pipeline_status": "running",
        "run_inputs": {},
        "node_logs": {},
        "node_errors": {},
        "workspace_dir": "",
    }
