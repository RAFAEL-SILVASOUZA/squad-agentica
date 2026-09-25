"""Função do nó de aprovação (D7 §7.1).

Dono: hitl-approval (FASE 7). Fontes de verdade:
- CONTRATO-TECNICO.md ADR-006 (Command(goto=<id real>)) e ADR-009 (sem efeitos
  colaterais antes do interrupt()).
- D7-human-in-the-loop.md §7.1.
- Spec 5.3 (semântica do interrupt() + roteamento pós-aprovação).

Contrato de interface (para o compiler, D5):
    create_approval_node(edge, source_node_id) -> Callable

O compiler importa esta factory e registra o nó no StateGraph via
``graph.add_node(f"approval_node_{edge.id}", fn)``. O compiler não precisa saber
o que a função faz internamente.

Semântica do LangGraph ``interrupt()`` (confirmada no spike, langgraph 0.2.61):
- ``interrupt(payload)`` é primitivo de nó: pausa a execução e salva checkpoint.
- Ao retomar (``Command(resume=...)``), o nó re-executa DO INÍCIO; o
  ``interrupt()`` agora retorna o valor de resume em vez de pausar.
- Consequência (V-02/ADR-009): qualquer efeito colateral ANTES do ``interrupt()``
  se repete. Por isso este nó NÃO tem efeitos colaterais antes do interrupt:
  apenas monta o payload (operação pura). A persistência da ApprovalRequest e a
  notificação são feitas pelo executor (hook de interrupção, ADR-009), que
  detecta a pausa no stream e faz upsert idempotente.

Roteamento pós-resposta (ADR-006: goto só com IDs reais de nó):
- aprovar   -> Command(goto=<target da edge>)
- rejeitar  -> Command(goto=<reject_target>)  (loop-back pro source por padrão,
              ou END se a aresta configurar reject_target="END")
- argumentar-> feedback do humano injetado no State (data[sourceNodeId].humanFeedback)
              + Command(goto=<target da edge>) -> o agente target retoma com a info.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from langgraph.graph import END
from langgraph.types import Command, interrupt

from app.compiler.graph_builder import PipelineEdge
from app.compiler.state import State

logger = logging.getLogger(__name__)

# Decisões válidas que o humano pode enviar via Command(resume=...).
# Mapeadas no endpoint POST /api/approvals/{id}/respond (spec 5.3).
DECISION_APPROVED = "approved"
DECISION_REJECTED = "rejected"
DECISION_REVISED = "revised"

# Key no State onde o feedback do humano é injetado (modo "argumentar").
# Convenção ADR-003: namespace por nodeId dentro de `data`.
HUMAN_FEEDBACK_KEY = "humanFeedback"


def _normalize_decision(resume_value: Any) -> str:
    """Normaliza o valor de resume para uma das três decisões.

    Aceita:
    - string: "approved" | "rejected" | "revised" (ou "revised"/"revised" sinônimos).
    - dict: {"decision": "...", "response": "..."} (formato do endpoint respond).

    Qualquer valor desconhecido é tratado como "approved" (comportamento
    conservador: segue o fluxo para o target). O endpoint responde sempre com
    uma das três decisões canônicas, então isto é só uma rede de segurança.
    """
    if isinstance(resume_value, str):
        value = resume_value.strip().lower()
    elif isinstance(resume_value, dict):
        value = str(resume_value.get("decision", "")).strip().lower()
    else:
        value = ""

    if value in (DECISION_REJECTED, "reject"):
        return DECISION_REJECTED
    if value in (DECISION_REVISED, "revised", "revised", "argument"):
        return DECISION_REVISED
    # "approved", "approve", ou qualquer valor vazio/desconhecido -> aprovar.
    return DECISION_APPROVED


def _extract_feedback(resume_value: Any) -> str:
    """Extrai o texto do feedback do humano (modo argumentar).

    Aceita dict {"response": "..."} ou string. Vazio se não houver.
    """
    if isinstance(resume_value, dict):
        return str(resume_value.get("response", "") or "")
    if isinstance(resume_value, str):
        return resume_value
    return ""


def create_approval_node(
    edge: PipelineEdge,
    source_node_id: str,
) -> Callable:
    """Factory do nó de aprovação (contrato de interface para o compiler, D5).

    Args:
        edge: A PipelineEdge com ``requires_approval=True``. Fornece
            ``target`` (destino ao aprovar), ``reject_target`` (destino ao
            rejeitar; default loop-back pro source), ``approval_message`` e
            ``approval_channel``.
        source_node_id: ID do nó source da edge (o agente que produziu o output
            que está sendo aprovado). Usado para o loop-back de rejeição e para
            namespacing do feedback no State.

    Returns:
        A função assíncrona do nó, pronta para ``graph.add_node(name, fn)``.
    """
    edge_id = edge.id
    approve_target = edge.target
    # ADR-006: rejectTarget configurável na aresta. Default: loop-back pro source.
    # "END" (ou None resolvida para source) é tratado explicitamente.
    reject_target = edge.reject_target or source_node_id
    message = edge.approval_message or "Aprovação necessária"

    async def approval_node(state: State, config: dict[str, Any]) -> Any:
        # ------------------------------------------------------------------
        # 1. Monta o payload (operação pura, SEM efeitos colaterais).
        #    ADR-009: nada aqui pode ter efeito colateral, porque o nó
        #    re-executa do início ao retomar.
        # ------------------------------------------------------------------
        source_data = state.get("data", {}).get(source_node_id, {})
        payload: dict[str, Any] = {
            "message": message,
            "edgeId": edge_id,
            "sourceNodeId": source_node_id,
            "targetNodeId": approve_target,
            "rejectTarget": reject_target,
            "approvalChannel": edge.approval_channel,
            # Contexto: o que o agente source produziu até aqui (spec 4.5).
            "context": source_data,
        }

        # ------------------------------------------------------------------
        # 2. interrupt(payload): pausa a execução e salva checkpoint.
        #    Ao retomar, retorna o valor de Command(resume=...).
        # ------------------------------------------------------------------
        resume_value = interrupt(payload)

        # ------------------------------------------------------------------
        # 3. Retomada: decide o roteamento (ADR-006: goto com IDs reais).
        #    Nenhum efeito colateral aqui: a persistência da ApprovalRequest e
        #    a notificação são responsabilidade do executor (hook, ADR-009).
        # ------------------------------------------------------------------
        decision = _normalize_decision(resume_value)

        if decision == DECISION_REJECTED:
            # Rejeitar: devolve ao source (loop-back) ou encerra (END).
            target = END if reject_target == END else reject_target
            logger.info(
                "approval rejected",
                extra={"edge_id": edge_id, "node_id": source_node_id, "goto": target},
            )
            return Command(goto=target)

        if decision == DECISION_REVISED:
            # Argumentar: injeta o feedback do humano no State (namespace do
            # source, ADR-003) e segue para o target. O agente target lê
            # data[sourceNodeId].humanFeedback e retoma com a informação.
            feedback = _extract_feedback(resume_value)
            logger.info(
                "approval revised (feedback injected)",
                extra={"edge_id": edge_id, "node_id": source_node_id, "goto": approve_target},
            )
            return Command(
                update={"data": {source_node_id: {HUMAN_FEEDBACK_KEY: feedback}}},
                goto=approve_target,
            )

        # Aprovado (default): segue para o target da edge.
        logger.info(
            "approval approved",
            extra={"edge_id": edge_id, "node_id": source_node_id, "goto": approve_target},
        )
        return Command(goto=approve_target)

    approval_node.__name__ = f"approval_node_{edge_id}"
    return approval_node


# Alias canônico (contrato D7: "D7 exporta approval_node_function").
# O compiler pode importar ``approval_node_function`` ou ``create_approval_node``.
approval_node_function = create_approval_node
