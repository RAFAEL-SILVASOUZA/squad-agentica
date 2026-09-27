/**
 * Validaçao de grafo no frontend (espelha as regras do compiler, spec 4.2 + PLANO-BACKEND pe-validator).
 *
 * O backend valida a verdade final em `POST /api/pipelines/validate` (dono: rt-executor).
 * Este modulo entrega verificacao local instantanea (painel de aresta + bloqueio do botao executar)
 * usando as mesmas regras, sem rede.
 */

import type {
  DataMapping,
  EdgeCondition,
  FlowAction,
  Pipeline,
  PipelineEdge,
  PipelineNode,
  PortDef,
} from "@/lib/types";

export interface ValidationError {
  rule: number;
  message: string;
  nodeId?: string;
  edgeId?: string;
}

const FLOW_ACTIONS: FlowAction[] = ["follow", "return", "finalize"];

export function flowActions(): FlowAction[] {
  return [...FLOW_ACTIONS];
}

function findPort(
  ports: PortDef[],
  name: string | undefined
): PortDef | undefined {
  if (!name) return undefined;
  return ports.find((p) => p.name === name);
}

/**
 * Valida uma data mapping localmente (regras 1-4).
 * Retorna a mensagem de erro ou null quando o mapeamento e coerente.
 */
export function validateDataMapping(
  dataMapping: DataMapping | undefined,
  sourceNode: Pick<PipelineNode, "agentSnapshot"> | undefined,
  targetNode: Pick<PipelineNode, "agentSnapshot"> | undefined
): string | null {
  if (!dataMapping || !dataMapping.sourceOutput || !dataMapping.targetInput) {
    return "Data edge exige sourceOutput e targetInput";
  }
  const src = findPort(sourceNode?.agentSnapshot.outputs ?? [], dataMapping.sourceOutput);
  if (!src) {
    return `sourceOutput "${dataMapping.sourceOutput}" não existe nos outputs do agente de origem`;
  }
  const tgt = findPort(targetNode?.agentSnapshot.inputs ?? [], dataMapping.targetInput);
  if (!tgt) {
    return `targetInput "${dataMapping.targetInput}" não existe nos inputs do agente de destino`;
  }
  if (src.type && tgt.type && src.type !== tgt.type) {
    return `tipo incompatível: "${src.type}" (sourceOutput) vs "${tgt.type}" (targetInput)`;
  }
  return null;
}

function conditionKey(condition: EdgeCondition | undefined): string {
  if (!condition) return "__unconditional__";
  const value = Array.isArray(condition.value)
    ? [...condition.value].sort().join("|")
    : condition.value;
  return `${condition.field}:${condition.operator}:${value}`;
}

/**
 * Valida o grafo completo (regras 1-11 da spec 4.2).
 * Regra 10 e apenas aviso (action sem flow edge); nao bloqueia.
 */
export function validateGraph(
  nodes: PipelineNode[],
  edges: PipelineEdge[],
  entryNodeId?: string
): ValidationError[] {
  const errors: ValidationError[] = [];
  const nodeById = new Map(nodes.map((n) => [n.id, n]));
  const flowEdges = edges.filter((e) => e.type === "flow");
  const dataEdges = edges.filter((e) => e.type === "data");

  // Regra 1-4: data edge exige dataMapping valida
  for (const e of dataEdges) {
    const source = nodeById.get(e.source);
    const target = nodeById.get(e.target);
    const problem = validateDataMapping(e.dataMapping, source, target);
    if (problem) {
      errors.push({ rule: 1, message: `${problem} (aresta ${e.source} -> ${e.target})`, edgeId: e.id });
    }
  }

  // Regra 6: input required sem data edge de nenhuma origem
  for (const node of nodes) {
    const requiredInputs = node.agentSnapshot.inputs.filter((p) => p.required);
    for (const input of requiredInputs) {
      const covered = dataEdges.some(
        (e) => e.target === node.id && e.dataMapping?.targetInput === input.name
      );
      if (!covered) {
        errors.push({
          rule: 6,
          message: `input required "${input.name}" de "${node.agentSnapshot.name}" não é atendido por nenhuma data edge`,
          nodeId: node.id,
        });
      }
    }
  }

  // Regra 8: no orfao (exceto entry) sem flow nem data de entrada
  const entryId = entryNodeId && nodeById.has(entryNodeId) ? entryNodeId : null;
  for (const node of nodes) {
    if (node.id === entryId) continue;
    const hasIncoming =
      flowEdges.some((e) => e.target === node.id) ||
      dataEdges.some((e) => e.target === node.id);
    if (!hasIncoming) {
      errors.push({
        rule: 8,
        message: `"${node.agentSnapshot.name}" é um nó órfão: sem flow edge nem data edge de entrada`,
        nodeId: node.id,
      });
    }
  }

  // Regra 9: entryNodeId inexistente (entry vazia = pipeline ainda sem grafo desenhado; nao erro aqui)
  if (entryNodeId && !nodeById.has(entryNodeId)) {
    errors.push({
      rule: 9,
      message: `entryNodeId "${entryNodeId}" não referencia um nó existente`,
    });
  }

  // Regra 11: duas flow edges identicas (mesmo par, mesma condition)
  const seen = new Map<string, string>();
  for (const e of flowEdges) {
    const pairKey = `${e.source}>${e.target}>${conditionKey(e.condition)}`;
    const first = seen.get(pairKey);
    if (first) {
      errors.push({
        rule: 11,
        message: `flow edges duplicadas entre ${e.source} e ${e.target} com a mesma condição`,
        edgeId: e.id,
      });
    } else {
      seen.set(pairKey, e.id);
    }
  }

  return errors;
}

/**
 * Converte a resposta do endpoint de validacao (`POST /api/pipelines/validate`,
 * 200 `{ valid: boolean, errors: [...] }`) para o formato local.
 * Tolerante: itens sem forma esperada viram mensagem genérica.
 */
export function normalizeServerValidation(
  payload: unknown
): { valid: boolean; errors: ValidationError[] } {
  const raw = payload as { valid?: boolean; errors?: unknown } | null;
  const rawErrors: unknown[] = Array.isArray(raw?.errors) ? raw.errors : [];
  const errors: ValidationError[] = rawErrors.map((item, index) => {
    if (item && typeof item === "object") {
      const o = item as Record<string, unknown>;
      return {
        rule: typeof o.rule === "number" ? o.rule : index + 1,
        message: typeof o.message === "string" ? o.message : String(o.error ?? o.message ?? "erro de validacao"),
        nodeId: typeof o.nodeId === "string" ? o.nodeId : undefined,
        edgeId: typeof o.edgeId === "string" ? o.edgeId : undefined,
      };
    }
    return { rule: index + 1, message: String(item) };
  });
  const valid = typeof raw?.valid === "boolean" ? raw.valid : errors.length === 0;
  return { valid, errors };
}

/** Extrai ids de nos e arestas com erro para destacar no canvas. */
export function errorIdSets(errors: ValidationError[]): {
  nodeIds: Set<string>;
  edgeIds: Set<string>;
} {
  const nodeIds = new Set<string>();
  const edgeIds = new Set<string>();
  for (const e of errors) {
    if (e.nodeId) nodeIds.add(e.nodeId);
    if (e.edgeId) edgeIds.add(e.edgeId);
  }
  return { nodeIds, edgeIds };
}

/** Payload mínimo aceito por `POST /api/pipelines/validate` (mesma forma do corpo de PUT). */
export function buildValidationPayload(
  pipeline: Pipeline,
  nodes: PipelineNode[],
  edges: PipelineEdge[]
): Pipeline {
  return {
    ...pipeline,
    nodes,
    edges,
    entryNodeId: pipeline.entryNodeId || (nodes.length > 0 ? nodes[0].id : ""),
  };
}
