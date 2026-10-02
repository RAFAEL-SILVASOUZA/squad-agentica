"use client";

import * as React from "react";
import { Plus, Trash2, Pencil, AlertTriangle, Link2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Agent, Pipeline, PipelineEdge, PipelineNode } from "@/lib/types";

/**
 * Ordenacao topologica dos nos do grafo (Kahn).
 *
 * Usa flow edges + data edges para definir a ordem. Nos que ficam num ciclo
 * (ou dependem de um) nao chegam a in-degree 0 e vao para o fim da ordem,
 * listados em `cyclic` para o aviso "Ha um ciclo envolvendo: A, B".
 */
export function topoOrder(
  nodes: PipelineNode[],
  edges: PipelineEdge[]
): { order: string[]; cyclic: string[] } {
  const nodeIds = nodes.map((n) => n.id);
  const idSet = new Set(nodeIds);
  const relevant = edges.filter((e) => idSet.has(e.source) && idSet.has(e.target));

  const inDegree = new Map<string, number>();
  const adjacency = new Map<string, string[]>();
  for (const id of nodeIds) {
    inDegree.set(id, 0);
    adjacency.set(id, []);
  }
  for (const e of relevant) {
    adjacency.get(e.source)!.push(e.target);
    inDegree.set(e.target, (inDegree.get(e.target) ?? 0) + 1);
  }

  const queue = nodeIds.filter((id) => inDegree.get(id) === 0);
  const order: string[] = [];
  const processed = new Set<string>();

  while (queue.length > 0) {
    const id = queue.shift()!;
    order.push(id);
    processed.add(id);
    for (const next of adjacency.get(id) ?? []) {
      const deg = (inDegree.get(next) ?? 0) - 1;
      inDegree.set(next, deg);
      if (deg === 0) queue.push(next);
    }
  }

  const cyclic = nodeIds.filter((id) => !processed.has(id));
  return { order: [...order, ...cyclic], cyclic };
}

interface StepsListProps {
  pipeline: Pipeline;
  agents: Agent[];
  onChange: (nodes: PipelineNode[], edges: PipelineEdge[]) => void;
  disabled?: boolean;
  /** Seleciona um nó para edição (abre o painel de propriedades). */
  onSelectNode?: (nodeId: string) => void;
}

/**
 * Modo lista de etapas do editor (abaixo de 768px, spec 3.6).
 *
 * Nos em ordem topologica, cada um com as entradas, as arestas e as acoes
 * Editar e Remover. Tem "Adicionar agente" e "Conectar a…" (cria flow edge).
 * O canvas nao aparece.
 */
export function StepsList({ pipeline, agents, onChange, disabled = false, onSelectNode }: StepsListProps) {
  const { nodes, edges } = pipeline;
  const { order, cyclic } = topoOrder(nodes, edges);
  const orderedNodes = order
    .map((id) => nodes.find((n) => n.id === id))
    .filter((n): n is PipelineNode => !!n);

  const [addAgentId, setAddAgentId] = React.useState("");
  const [connectSource, setConnectSource] = React.useState("");
  const [connectTarget, setConnectTarget] = React.useState("");
  const [confirmDelete, setConfirmDelete] = React.useState<string | null>(null);

  const handleAddAgent = () => {
    const agent = agents.find((a) => a.id === addAgentId);
    if (!agent) return;
    const nodeId = `node-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const newNode: PipelineNode = {
      id: nodeId,
      agentId: agent.id,
      position: { x: 0, y: nodes.length * 120 },
      label: agent.name,
      agentSnapshot: {
        agentId: agent.id,
        version: 1,
        name: agent.name,
        description: agent.description,
        prompt: agent.prompt,
        strategy: agent.strategy,
        skills: agent.skills,
        tools: agent.tools,
        mcpServers: agent.mcpServers,
        knowledge: agent.knowledge,
        integrations: agent.integrations,
        inputs: agent.inputs,
        outputs: agent.outputs,
        actions: agent.actions,
        model: agent.model,
        maxIterations: agent.maxIterations,
        timeout: agent.timeout,
        shellAccess: agent.shellAccess,
      },
    };
    onChange([...nodes, newNode], edges);
    setAddAgentId("");
  };

  const handleConnect = () => {
    if (!connectSource || !connectTarget || connectSource === connectTarget) return;
    const newEdge: PipelineEdge = {
      id: `edge-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      type: "flow",
      source: connectSource,
      target: connectTarget,
      requiresApproval: false,
    };
    onChange(nodes, [...edges, newEdge]);
    setConnectSource("");
    setConnectTarget("");
  };

  const handleDeleteNode = (nodeId: string) => {
    const newNodes = nodes.filter((n) => n.id !== nodeId);
    const newEdges = edges.filter((e) => e.source !== nodeId && e.target !== nodeId);
    onChange(newNodes, newEdges);
    setConfirmDelete(null);
  };

  const nodeLabel = (id: string) =>
    nodes.find((n) => n.id === id)?.agentSnapshot.name ?? id;

  return (
    <div
      data-testid="steps-list"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 12,
        padding: 12,
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius)",
      }}
    >
      <h2 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: "var(--text)" }}>
        Etapas
      </h2>

      {cyclic.length > 0 && (
        <div
          role="alert"
          style={{
            display: "flex",
            gap: 6,
            alignItems: "flex-start",
            padding: "8px 10px",
            background: "var(--warning-subtle, rgba(255,193,7,0.12))",
            border: "1px solid var(--warning)",
            borderRadius: "var(--radius-sm)",
            fontSize: 12,
            color: "var(--text)",
          }}
        >
          <AlertTriangle size={14} aria-hidden="true" style={{ flexShrink: 0, marginTop: 1 }} />
          <span>
            Há um ciclo envolvendo: {cyclic.map(nodeLabel).join(", ")}
          </span>
        </div>
      )}

      {orderedNodes.length === 0 ? (
        <p style={{ margin: 0, fontSize: 12, color: "var(--text-muted)" }}>
          Nenhuma etapa. Adicione um agente para começar.
        </p>
      ) : (
        <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 8 }}>
          {orderedNodes.map((node, idx) => {
            const incoming = edges.filter((e) => e.target === node.id);
            const outgoing = edges.filter((e) => e.source === node.id);
            return (
              <li
                key={node.id}
                data-testid={`step-${node.id}`}
                style={{
                  padding: 10,
                  background: "var(--bg-elevated)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius-sm)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  <span
                    style={{
                      width: 20,
                      height: 20,
                      borderRadius: "50%",
                      background: "var(--accent-subtle)",
                      color: "var(--accent)",
                      fontSize: 11,
                      fontWeight: 600,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                    }}
                  >
                    {idx + 1}
                  </span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text)", flex: 1, minWidth: 0 }}>
                    {node.agentSnapshot.name}
                  </span>
                  <button
                    type="button"
                    onClick={() => setConfirmDelete(node.id)}
                    disabled={disabled}
                    aria-label={`Remover ${node.agentSnapshot.name}`}
                    style={{ border: "none", background: "none", color: "var(--text-muted)", cursor: "pointer", padding: 4, display: "flex" }}
                  >
                    <Trash2 size={14} aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    disabled={disabled}
                    aria-label={`Editar ${node.agentSnapshot.name}`}
                    onClick={() => onSelectNode?.(node.id)}
                    style={{ border: "none", background: "none", color: "var(--text-muted)", cursor: "pointer", padding: 4, display: "flex" }}
                  >
                    <Pencil size={14} aria-hidden="true" />
                  </button>
                </div>

                {confirmDelete === node.id && (
                  <div
                    role="alertdialog"
                    style={{
                      display: "flex",
                      gap: 8,
                      alignItems: "center",
                      padding: "6px 8px",
                      marginBottom: 6,
                      background: "var(--error-subtle, rgba(255,59,48,0.1))",
                      border: "1px solid var(--error)",
                      borderRadius: "var(--radius-sm)",
                      fontSize: 12,
                    }}
                  >
                    <span style={{ flex: 1 }}>Excluir esta etapa?</span>
                    <button
                      type="button"
                      onClick={() => handleDeleteNode(node.id)}
                      style={{
                        padding: "4px 10px",
                        fontSize: 12,
                        fontWeight: 600,
                        color: "#fff",
                        background: "var(--error)",
                        border: "1px solid var(--error)",
                        borderRadius: "var(--radius-sm)",
                        cursor: "pointer",
                      }}
                    >
                      Confirmar
                    </button>
                    <Button size="sm" onClick={() => setConfirmDelete(null)}>
                      Cancelar
                    </Button>
                  </div>
                )}

                {(node.agentSnapshot.inputs?.length ?? 0) > 0 && (
                  <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 4 }}>
                    <strong>Entradas:</strong>{" "}
                    {node.agentSnapshot.inputs.map((i) => i.name).join(", ")}
                  </div>
                )}

                {incoming.length > 0 && (
                  <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 4 }}>
                    <strong>Recebe de:</strong>{" "}
                    {incoming.map((e) => `${nodeLabel(e.source)} (${e.type})`).join(", ")}
                  </div>
                )}
                {outgoing.length > 0 && (
                  <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                    <strong>Envia para:</strong>{" "}
                    {outgoing.map((e) => `${nodeLabel(e.target)} (${e.type})`).join(", ")}
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      )}

      {/* Adicionar agente */}
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <select
          value={addAgentId}
          disabled={disabled}
          onChange={(e) => setAddAgentId(e.target.value)}
          aria-label="Escolher agente para adicionar"
          style={{
            flex: 1,
            padding: "8px 10px",
            borderRadius: "var(--radius-sm)",
            border: "1px solid var(--border)",
            background: "var(--bg-elevated)",
            color: "var(--text)",
            fontSize: 12,
          }}
        >
          <option value="">Escolher agente…</option>
          {agents.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
        <Button size="sm" onClick={handleAddAgent} disabled={disabled || !addAgentId} aria-label="Adicionar agente">
          <Plus size={13} aria-hidden="true" />
          Adicionar agente
        </Button>
      </div>

      {/* Conectar a… */}
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <Link2 size={14} aria-hidden="true" style={{ color: "var(--text-muted)" }} />
        <select
          value={connectSource}
          disabled={disabled}
          onChange={(e) => setConnectSource(e.target.value)}
          aria-label="Conectar de"
          style={{
            flex: 1,
            minWidth: 100,
            padding: "8px 10px",
            borderRadius: "var(--radius-sm)",
            border: "1px solid var(--border)",
            background: "var(--bg-elevated)",
            color: "var(--text)",
            fontSize: 12,
          }}
        >
          <option value="">De…</option>
          {nodes.map((n) => (
            <option key={n.id} value={n.id}>
              {n.agentSnapshot.name}
            </option>
          ))}
        </select>
        <select
          value={connectTarget}
          disabled={disabled}
          onChange={(e) => setConnectTarget(e.target.value)}
          aria-label="Conectar para"
          style={{
            flex: 1,
            minWidth: 100,
            padding: "8px 10px",
            borderRadius: "var(--radius-sm)",
            border: "1px solid var(--border)",
            background: "var(--bg-elevated)",
            color: "var(--text)",
            fontSize: 12,
          }}
        >
          <option value="">Para…</option>
          {nodes.map((n) => (
            <option key={n.id} value={n.id}>
              {n.agentSnapshot.name}
            </option>
          ))}
        </select>
        <Button
          size="sm"
          onClick={handleConnect}
          disabled={disabled || !connectSource || !connectTarget || connectSource === connectTarget}
          aria-label="Conectar a"
        >
          Conectar a…
        </Button>
      </div>
    </div>
  );
}
