"use client";

import * as React from "react";
import { X, Trash2, AlertCircle, ExternalLink, GitBranch } from "lucide-react";

import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { EdgePanelContent } from "@/components/EdgePanel";
import type { ValidationError } from "./validation";
import type { Pipeline, PipelineEdge, PipelineNode } from "@/lib/types";

export interface PropertiesPanelProps {
  pipeline: Pipeline;
  selection: { nodeId?: string; edgeId?: string } | null;
  onChangeNode: (node: PipelineNode) => void;
  onChangeEdge: (edge: PipelineEdge) => void;
  onDeleteNode: (nodeId: string) => void;
  onDeleteEdge: (edgeId: string) => void;
  /** Deseleciona (fecha o painel de no/aresta). */
  onClose?: () => void;
  /** Seleciona um nó (usado pelos botões de erro de validação). */
  onSelectNode?: (nodeId: string) => void;
  errors?: ValidationError[];
  disabled?: boolean;
}

/**
 * Painel de propriedades do editor de pipeline (spec 3.6).
 *
 * Três modos conforme a seleção:
 * - sem seleção: "Pipeline" — nome, descrição, repositório, nó de entrada e validação;
 * - nó: agente (com link), "Entradas" com select por entrada, arestas que saem e "Excluir nó";
 * - aresta: reusa EdgePanelContent (tipo, condição, mapeamento, aprovação) + "Excluir aresta".
 */
export function PropertiesPanel({
  pipeline,
  selection,
  onChangeNode,
  onChangeEdge,
  onDeleteNode,
  onDeleteEdge,
  onClose,
  onSelectNode,
  errors = [],
  disabled = false,
}: PropertiesPanelProps) {
  const router = useRouter();
  const [confirmDeleteNode, setConfirmDeleteNode] = React.useState(false);
  const [confirmDeleteEdge, setConfirmDeleteEdge] = React.useState(false);

  React.useEffect(() => {
    setConfirmDeleteNode(false);
    setConfirmDeleteEdge(false);
  }, [selection]);

  const selectedNode = selection?.nodeId
    ? pipeline.nodes.find((n) => n.id === selection.nodeId)
    : undefined;
  const selectedEdge = selection?.edgeId
    ? pipeline.edges.find((e) => e.id === selection.edgeId)
    : undefined;

  const panelStyle: React.CSSProperties = {
    width: "100%",
    display: "flex",
    flexDirection: "column",
    background: "var(--bg-elevated)",
    border: "1px solid var(--border)",
    borderRadius: "var(--radius)",
    overflow: "hidden",
    fontSize: 12,
  };

  const headerStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "10px 12px",
    borderBottom: "1px solid var(--border)",
    fontWeight: 600,
    fontSize: 13,
    color: "var(--text)",
  };

  const bodyStyle: React.CSSProperties = {
    padding: 12,
    display: "flex",
    flexDirection: "column",
    gap: 10,
    overflowY: "auto",
  };

  // ── Modo: Pipeline (sem seleção) ──────────────────────────────────────
  if (!selectedNode && !selectedEdge) {
    const nodeErrors = errors.filter((e) => !e.edgeId);
    return (
      <div data-testid="properties-panel" style={panelStyle}>
        <div style={headerStyle}>
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <GitBranch size={14} aria-hidden="true" />
            Pipeline
          </span>
        </div>
        <div style={bodyStyle}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.5px", color: "var(--text-muted)", marginBottom: 4 }}>
              Nome
            </div>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>
              {pipeline.name}
            </div>
          </div>
          {pipeline.description && (
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.5px", color: "var(--text-muted)", marginBottom: 4 }}>
                Descrição
              </div>
              <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                {pipeline.description}
              </div>
            </div>
          )}
          {pipeline.repository && (
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.5px", color: "var(--text-muted)", marginBottom: 4 }}>
                Repositório
              </div>
              <div style={{ fontSize: 12, color: "var(--text-secondary)", fontFamily: "monospace" }}>
                {pipeline.repository.fullName}
              </div>
            </div>
          )}
          {pipeline.nodes.length > 0 && (
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.5px", color: "var(--text-muted)", marginBottom: 4 }}>
                Nó de entrada
              </div>
              <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                {pipeline.nodes.find((n) => n.id === pipeline.entryNodeId)?.agentSnapshot.name ??
                  pipeline.nodes[0]?.agentSnapshot.name ??
                  "—"}
              </div>
            </div>
          )}
          {nodeErrors.length > 0 && (
            <div
              role="alert"
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 6,
                paddingTop: 8,
                borderTop: "1px solid var(--border-subtle)",
              }}
            >
              {nodeErrors.map((e, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => {
                    if (e.nodeId) onSelectNode?.(e.nodeId);
                  }}
                  style={{
                    display: "flex",
                    gap: 6,
                    alignItems: "flex-start",
                    color: "var(--error)",
                    fontSize: 11,
                    margin: 0,
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    textAlign: "left",
                    padding: 0,
                  }}
                >
                  <AlertCircle size={12} aria-hidden="true" style={{ flexShrink: 0, marginTop: 1 }} />
                  {e.message}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  // ── Modo: Nó selecionado ──────────────────────────────────────────────
  if (selectedNode) {
    const node = selectedNode;
    const nodeErrors = errors.filter((e) => e.nodeId === node.id);
    const outgoingEdges = pipeline.edges.filter((e) => e.source === node.id);
    const otherNodes = pipeline.nodes.filter((n) => n.id !== node.id);

    // Para cada input do nó, determina a origem atual (data edge ou "run")
    const inputSources = node.agentSnapshot.inputs.map((input) => {
      const dataEdge = pipeline.edges.find(
        (e) =>
          e.type === "data" &&
          e.target === node.id &&
          e.dataMapping?.targetInput === input.name
      );
      if (dataEdge) {
        return {
          input,
          value: `${dataEdge.source}:${dataEdge.dataMapping!.sourceOutput}`,
        };
      }
      return { input, value: "run" };
    });

    const handleInputSourceChange = (inputName: string, value: string) => {
      // Remove data edge existente para este input
      const remainingEdges = pipeline.edges.filter(
        (e) =>
          !(
            e.type === "data" &&
            e.target === node.id &&
            e.dataMapping?.targetInput === inputName
          )
      );

      if (value === "run") {
        // Sem data edge: entrada do run
        return;
      }

      const [sourceNodeId, sourceOutput] = value.split(":");
      const newEdge: PipelineEdge = {
        id: `edge-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        type: "data",
        source: sourceNodeId,
        target: node.id,
        requiresApproval: false,
        dataMapping: { sourceOutput, targetInput: inputName },
      };
      onChangeEdge(newEdge);
    };

    return (
      <div data-testid="properties-panel" style={panelStyle}>
        <div style={headerStyle}>
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {node.agentSnapshot.name}
          </span>
          <button
            type="button"
            onClick={() => router.push(`/agents/${node.agentId}`)}
            aria-label={`Abrir agente ${node.agentSnapshot.name}`}
            style={{ border: "none", background: "none", color: "var(--text-muted)", cursor: "pointer", padding: 0, display: "flex" }}
          >
            <ExternalLink size={14} aria-hidden="true" />
          </button>
        </div>
        <div style={bodyStyle}>
          {/* Agente */}
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.5px", color: "var(--text-muted)", marginBottom: 4 }}>
              Agente
            </div>
            <button
              type="button"
              onClick={() => router.push(`/agents/${node.agentId}`)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                fontSize: 12,
                color: "var(--accent)",
                background: "none",
                border: "none",
                cursor: "pointer",
                padding: 0,
                textDecoration: "underline",
              }}
            >
              {node.agentSnapshot.name}
              <ExternalLink size={11} aria-hidden="true" />
            </button>
          </div>

          {/* Entradas */}
          {node.agentSnapshot.inputs.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.5px", color: "var(--text-muted)" }}>
                Entradas
              </div>
              {inputSources.map(({ input, value }) => (
                <div key={input.name} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <label
                    htmlFor={`input-${node.id}-${input.name}`}
                    style={{ fontSize: 12, color: "var(--text-secondary)" }}
                  >
                    {input.name}
                    {input.required && <span style={{ color: "var(--error)" }}> *</span>}
                  </label>
                  <select
                    id={`input-${node.id}-${input.name}`}
                    value={value}
                    disabled={disabled}
                    onChange={(e) => handleInputSourceChange(input.name, e.target.value)}
                    style={{
                      padding: "6px 8px",
                      borderRadius: "var(--radius-sm)",
                      border: "1px solid var(--border)",
                      background: "var(--bg-elevated)",
                      color: "var(--text)",
                      fontSize: 12,
                    }}
                  >
                    <option value="run">entrada do run</option>
                    {otherNodes.flatMap((other) =>
                      other.agentSnapshot.outputs.map((out) => (
                        <option key={`${other.id}:${out.name}`} value={`${other.id}:${out.name}`}>
                          Saída &apos;{out.name}&apos; de {other.agentSnapshot.name}
                        </option>
                      ))
                    )}
                  </select>
                </div>
              ))}
            </div>
          )}

          {/* Arestas que saem */}
          {outgoingEdges.length > 0 && (
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.5px", color: "var(--text-muted)", marginBottom: 4 }}>
                Arestas que saem
              </div>
              <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 4 }}>
                {outgoingEdges.map((e) => {
                  const target = pipeline.nodes.find((n) => n.id === e.target);
                  return (
                    <li key={e.id} style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                      → {target?.agentSnapshot.name ?? e.target} ({e.type})
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {/* Erros do nó */}
          {nodeErrors.length > 0 && (
            <div role="alert" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {nodeErrors.map((e, i) => (
                <p key={i} style={{ display: "flex", gap: 6, alignItems: "flex-start", color: "var(--error)", fontSize: 11, margin: 0 }}>
                  <AlertCircle size={12} aria-hidden="true" style={{ flexShrink: 0, marginTop: 1 }} />
                  {e.message}
                </p>
              ))}
            </div>
          )}

          {/* Excluir nó */}
          <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: 8 }}>
            {confirmDeleteNode ? (
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span style={{ flex: 1, fontSize: 12, color: "var(--error)" }}>
                  Excluir este nó?
                </span>
                <button
                  type="button"
                  onClick={() => onDeleteNode(node.id)}
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
                <Button size="sm" onClick={() => setConfirmDeleteNode(false)}>
                  Cancelar
                </Button>
              </div>
            ) : (
              <Button
                size="sm"
                onClick={() => setConfirmDeleteNode(true)}
                disabled={disabled}
                style={{ color: "var(--error)" }}
              >
                <Trash2 size={12} aria-hidden="true" />
                Excluir nó
              </Button>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ── Modo: Aresta selecionada ──────────────────────────────────────────
  if (selectedEdge) {
    const edge = selectedEdge;
    const edgeErrors = errors
      .filter((e) => e.edgeId === edge.id)
      .map((e) => e.message);
    const sourceNode = pipeline.nodes.find((n) => n.id === edge.source);
    const targetNode = pipeline.nodes.find((n) => n.id === edge.target);

    return (
      <div
        data-testid="properties-panel"
        role="region"
        aria-label={`Configuração da aresta ${sourceNode?.agentSnapshot.name ?? edge.source} para ${targetNode?.agentSnapshot.name ?? edge.target}`}
        style={panelStyle}
      >
        <div style={headerStyle}>
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {sourceNode?.agentSnapshot.name ?? edge.source} →{" "}
            {targetNode?.agentSnapshot.name ?? edge.target}
          </span>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label="Fechar painel da aresta"
              style={{ border: "none", background: "none", color: "var(--text-muted)", cursor: "pointer", padding: 0, display: "flex" }}
            >
              <X size={14} aria-hidden="true" />
            </button>
          )}
        </div>
        <div style={bodyStyle}>
          <EdgePanelContent
            edge={edge}
            nodes={pipeline.nodes}
            onChange={onChangeEdge}
            errors={edgeErrors}
            disabled={disabled}
          />
          <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: 8 }}>
            {confirmDeleteEdge ? (
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span style={{ flex: 1, fontSize: 12, color: "var(--error)" }}>
                  Excluir esta aresta?
                </span>
                <button
                  type="button"
                  onClick={() => onDeleteEdge(edge.id)}
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
                <Button size="sm" onClick={() => setConfirmDeleteEdge(false)}>
                  Cancelar
                </Button>
              </div>
            ) : (
              <Button
                size="sm"
                onClick={() => setConfirmDeleteEdge(true)}
                disabled={disabled}
                style={{ color: "var(--error)" }}
              >
                <Trash2 size={12} aria-hidden="true" />
                Excluir aresta
              </Button>
            )}
          </div>
        </div>
      </div>
    );
  }

  return null;
}
