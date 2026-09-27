"use client";

import * as React from "react";
import {
  ReactFlow,
  Background,
  MiniMap,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  addEdge,
  type Connection,
  type Edge,
  type Node,
  type NodeTypes,
  type EdgeTypes,
  type OnSelectionChangeParams,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Plus,
  ZoomIn,
  ZoomOut,
  Maximize,
  Undo2,
  Redo2,
  Save,
  Trash2,
} from "lucide-react";
import { AgentNode, type AgentNodeData } from "./flow/agent-node";
import { PipelineEdgeComponent, type PipelineEdgeData } from "./flow/pipeline-edge";
import { AgentPalette } from "./flow/agent-palette";
import { Button } from "./ui/button";
import { useToast } from "./ui/toast";
import type { Agent, Pipeline, PipelineNode, PipelineEdge } from "@/lib/types";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface FlowEditorProps {
  pipeline: Pipeline;
  agents: Agent[];
  onSave: (nodes: PipelineNode[], edges: PipelineEdge[]) => Promise<void>;
  onEdgeSelect?: (edge: PipelineEdge | null) => void;
  /**
   * Notifica a pagina quando uma aresta muda via painel (fe-flow-edges).
   * O canvas atualiza a aresta localmente; a pagina revalida e persiste.
   */
  onEdgeChange?: (edge: PipelineEdge) => void;
  /**
   * Notifica a pagina quando o grafo muda (nos/arestas), com debounce interno.
   * A pagina usa para revalidacao em tempo real (fe-flow-edges).
   */
  onGraphChange?: (nodes: PipelineNode[], edges: PipelineEdge[]) => void;
  /** Slot for the edge panel (fe-flow-edges will plug in here). */
  edgePanelSlot?: React.ReactNode;
  disabled?: boolean;
  /**
   * Ids com erro de validacao (fe-flow-edges). Nossos/arestas destacadas
   * em var(--error) para o usuario localizar o problema no canvas.
   */
  errorIdSets?: { nodeIds: Set<string>; edgeIds: Set<string> };
}

interface HistoryEntry {
  nodes: Node<AgentNodeData>[];
  edges: Edge<PipelineEdgeData>[];
}

// ─── Conversion helpers ──────────────────────────────────────────────────────

function pipelineToFlowNodes(pipeline: Pipeline): Node<AgentNodeData>[] {
  return pipeline.nodes.map((pn) => ({
    id: pn.id,
    type: "agent",
    position: pn.position,
    data: {
      label: pn.label ?? pn.agentSnapshot.name,
      agentSnapshot: pn.agentSnapshot,
      inputs: pn.agentSnapshot.inputs,
      outputs: pn.agentSnapshot.outputs,
      isEntry: pn.id === pipeline.entryNodeId,
    },
  }));
}

function pipelineToFlowEdges(pipeline: Pipeline): Edge<PipelineEdgeData>[] {
  return pipeline.edges.map((pe) => ({
    id: pe.id,
    source: pe.source,
    target: pe.target,
    type: "pipeline",
    data: {
      edgeType: pe.type,
      condition: pe.condition,
      label: pe.label,
      requiresApproval: pe.requiresApproval,
      dataMapping: pe.dataMapping,
    },
  }));
}

function flowNodesToPipelineNodes(nodes: Node<AgentNodeData>[]): PipelineNode[] {
  return nodes.map((n) => ({
    id: n.id,
    agentId: n.data.agentSnapshot.agentId,
    position: { x: n.position.x, y: n.position.y },
    label: n.data.label,
    agentSnapshot: n.data.agentSnapshot,
  }));
}

function flowEdgesToPipelineEdges(edges: Edge<PipelineEdgeData>[]): PipelineEdge[] {
  return edges.map((e) => ({
    id: e.id,
    type: (e.data?.edgeType ?? "flow") as "flow" | "data",
    source: e.source,
    target: e.target,
    condition: e.data?.condition as PipelineEdge["condition"],
    label: e.data?.label,
    requiresApproval: e.data?.requiresApproval ?? false,
    approvalChannel: e.data?.approvalChannel as PipelineEdge["approvalChannel"],
    approvalMessage: e.data?.approvalMessage as PipelineEdge["approvalMessage"],
    dataMapping: e.data?.dataMapping as PipelineEdge["dataMapping"],
  }));
}

// ─── Node/Edge type registries ───────────────────────────────────────────────

const nodeTypes: NodeTypes = {
  agent: AgentNode as unknown as NodeTypes["agent"],
};

const edgeTypes: EdgeTypes = {
  pipeline: PipelineEdgeComponent as unknown as EdgeTypes["pipeline"],
};

// ─── Inner editor (needs ReactFlowProvider context) ──────────────────────────

function FlowEditorInner({
  pipeline,
  agents,
  onSave,
  onEdgeSelect,
  onEdgeChange,
  onGraphChange,
  edgePanelSlot,
  disabled,
  errorIdSets,
  forwardedRef,
}: FlowEditorProps & { forwardedRef?: React.Ref<FlowEditorHandle> }) {
  const { addToast } = useToast();
  const { zoomIn, zoomOut, fitView, screenToFlowPosition } = useReactFlow();

  const [nodes, setNodes, onNodesChange] = useNodesState<Node<AgentNodeData>>(
    pipelineToFlowNodes(pipeline)
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge<PipelineEdgeData>>(
    pipelineToFlowEdges(pipeline)
  );

  // Palette state
  const [showPalette, setShowPalette] = React.useState(false);

  // History for undo/redo
  const [history, setHistory] = React.useState<HistoryEntry[]>([]);
  const [historyIndex, setHistoryIndex] = React.useState(-1);

  // Save state
  const [saving, setSaving] = React.useState(false);
  const [dirty, setDirty] = React.useState(false);



  // Push to history
  const pushHistory = React.useCallback(
    (newNodes: Node<AgentNodeData>[], newEdges: Edge<PipelineEdgeData>[]) => {
      setHistory((prev) => {
        const trimmed = prev.slice(0, historyIndex + 1);
        const next = [...trimmed, { nodes: newNodes, edges: newEdges }];
        // Cap history at 50 entries
        return next.length > 50 ? next.slice(next.length - 50) : next;
      });
      setHistoryIndex((prev) => {
        const newLen = Math.min(prev + 2, 50) - 1;
        return newLen;
      });
      setDirty(true);
    },
    [historyIndex]
  );

  // Undo
  const handleUndo = React.useCallback(() => {
    if (historyIndex <= 0) return;
    const entry = history[historyIndex - 1];
    setNodes(entry.nodes);
    setEdges(entry.edges);
    setHistoryIndex(historyIndex - 1);
    setDirty(true);
  }, [history, historyIndex, setNodes, setEdges]);

  // Redo
  const handleRedo = React.useCallback(() => {
    if (historyIndex >= history.length - 1) return;
    const entry = history[historyIndex + 1];
    setNodes(entry.nodes);
    setEdges(entry.edges);
    setHistoryIndex(historyIndex + 1);
    setDirty(true);
  }, [history, historyIndex, setNodes, setEdges]);

  // Keyboard shortcuts (defined after handleSave to capture correct reference)
  // See effect below handleSave definition.

  // Connection handler
  const onConnect = React.useCallback(
    (connection: Connection) => {
      const newEdge: Edge<PipelineEdgeData> = {
        ...connection,
        id: `edge-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        type: "pipeline",
        data: {
          edgeType: "flow",
          requiresApproval: false,
        },
      };
      const newEdges = addEdge(newEdge, edges);
      setEdges(newEdges);
      pushHistory(nodes, newEdges);
    },
    [edges, nodes, setEdges, pushHistory]
  );

  // Node change handler (with history)
  const onNodesChangeWrapper = React.useCallback(
    (changes: Parameters<typeof onNodesChange>[0]) => {
      onNodesChange(changes);
      // Only push history for structural changes (add/remove), not drag
      const hasAddOrRemove = changes.some(
        (c) => c.type === "add" || c.type === "remove"
      );
      if (hasAddOrRemove) {
        // Defer to get updated state
        setTimeout(() => {
          pushHistory(nodes, edges);
        }, 0);
      }
    },
    [onNodesChange, nodes, edges, pushHistory]
  );

  // Edge change handler (with history)
  const onEdgesChangeWrapper = React.useCallback(
    (changes: Parameters<typeof onEdgesChange>[0]) => {
      onEdgesChange(changes);
      const hasRemove = changes.some((c) => c.type === "remove");
      if (hasRemove) {
        setTimeout(() => {
          pushHistory(nodes, edges);
        }, 0);
      }
    },
    [onEdgesChange, nodes, edges, pushHistory]
  );

  // Add agent from palette
  const handleAddAgent = React.useCallback(
    (agent: Agent) => {
      const nodeId = `node-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const newNode: Node<AgentNodeData> = {
        id: nodeId,
        type: "agent",
        position: { x: 250 + Math.random() * 100, y: 200 + Math.random() * 100 },
        data: {
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
          inputs: agent.inputs,
          outputs: agent.outputs,
          isEntry: nodes.length === 0,
        },
      };
      const newNodes = [...nodes, newNode];
      setNodes(newNodes);
      pushHistory(newNodes, edges);
      setShowPalette(false);
    },
    [nodes, edges, setNodes, pushHistory]
  );

  // Graph change -> notify page (fe-flow-edges revalidation, debounced)
  const onGraphChangeRef = React.useRef(onGraphChange);
  onGraphChangeRef.current = onGraphChange;
  React.useEffect(() => {
    if (!onGraphChangeRef.current) return;
    const t = setTimeout(() => {
      onGraphChangeRef.current?.(
        flowNodesToPipelineNodes(nodes),
        flowEdgesToPipelineEdges(edges)
      );
    }, 150);
    return () => clearTimeout(t);
  }, [nodes, edges]);

  // Edge change from EdgePanel (fe-flow-edges): update the edge in place
  // E13: este callback é o núcleo — a pagina o expõe via ref.updateEdge.
  const handleEdgeChange = React.useCallback(
    (edge: PipelineEdge) => {
      const newEdges = edges.map((e) =>
        e.id === edge.id
          ? {
              ...e,
              data: {
                edgeType: edge.type,
                condition: edge.condition,
                label: edge.label,
                requiresApproval: edge.requiresApproval,
                dataMapping: edge.dataMapping,
                approvalChannel: edge.approvalChannel,
                approvalMessage: edge.approvalMessage,
              },
            }
          : e
      );
      setEdges(newEdges);
      pushHistory(nodes, newEdges);
      onEdgeChange?.(edge);
    },
    [edges, nodes, setEdges, pushHistory, onEdgeChange]
  );

  // E13: expõe updateEdge para a pagina (EdgePanel -> canvas interno)
  React.useImperativeHandle(
    forwardedRef,
    () => ({
      updateEdge: (edge: PipelineEdge) => {
        handleEdgeChange(edge);
      },
    }),
    [handleEdgeChange]
  );

  // Highlight edges with validation errors (fe-flow-edges)
  const displayEdges = React.useMemo(() => {
    if (!errorIdSets?.edgeIds.size) return edges;
    return edges.map((e) => {
      if (!errorIdSets.edgeIds.has(e.id)) return e;
      const data = (e.data ?? { edgeType: "flow" as const }) as PipelineEdgeData;
      return { ...e, data: { ...data, hasError: true } };
    });
  }, [edges, errorIdSets]);

  // Delete selected node
  const handleDeleteNode = React.useCallback(() => {
    const selectedNode = nodes.find((n) => n.selected);
    if (!selectedNode) return;
    const newNodes = nodes.filter((n) => n.id !== selectedNode.id);
    const newEdges = edges.filter(
      (e) => e.source !== selectedNode.id && e.target !== selectedNode.id
    );
    setNodes(newNodes);
    setEdges(newEdges);
    pushHistory(newNodes, newEdges);
  }, [nodes, edges, setNodes, setEdges, pushHistory]);

  // Save
  const handleSave = React.useCallback(async () => {
    if (disabled || !dirty) return;
    setSaving(true);
    try {
      const pipelineNodes = flowNodesToPipelineNodes(nodes);
      const pipelineEdges = flowEdgesToPipelineEdges(edges);
      await onSave(pipelineNodes, pipelineEdges);
      setDirty(false);
      addToast("success", "Pipeline salvo");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Falha ao salvar o pipeline";
      addToast("error", message);
    } finally {
      setSaving(false);
    }
  }, [nodes, edges, onSave, dirty, disabled, addToast]);

  // Keyboard shortcuts
  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "z" && !e.shiftKey) {
        e.preventDefault();
        handleUndo();
      } else if ((e.ctrlKey || e.metaKey) && (e.key === "y" || (e.key === "z" && e.shiftKey))) {
        e.preventDefault();
        handleRedo();
      } else if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        handleSave();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [handleUndo, handleRedo, handleSave]);

  // Selection change → notify parent
  const onSelectionChange = React.useCallback(
    ({ nodes: selectedNodes, edges: selectedEdges }: OnSelectionChangeParams) => {
      if (onEdgeSelect) {
        if (selectedEdges.length > 0) {
          const edge = selectedEdges[0];
          const d = edge.data as unknown as PipelineEdgeData | undefined;
          onEdgeSelect({
            id: edge.id,
            type: (d?.edgeType ?? "flow") as "flow" | "data",
            source: edge.source,
            target: edge.target,
            condition: d?.condition as PipelineEdge["condition"],
            label: d?.label,
            requiresApproval: d?.requiresApproval ?? false,
            dataMapping: d?.dataMapping as PipelineEdge["dataMapping"],
          });
        } else {
          onEdgeSelect(null);
        }
      }
    },
    [onEdgeSelect]
  );

  // Drop handler for drag from palette
  const onDrop = React.useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const agentId = e.dataTransfer.getData("application/agent-id");
      if (!agentId) return;
      const agent = agents.find((a) => a.id === agentId);
      if (!agent) return;

      const position = screenToFlowPosition({
        x: e.clientX,
        y: e.clientY,
      });

      const nodeId = `node-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const newNode: Node<AgentNodeData> = {
        id: nodeId,
        type: "agent",
        position,
        data: {
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
          inputs: agent.inputs,
          outputs: agent.outputs,
          isEntry: nodes.length === 0,
        },
      };
      const newNodes = [...nodes, newNode];
      setNodes(newNodes);
      pushHistory(newNodes, edges);
    },
    [agents, nodes, edges, setNodes, pushHistory, screenToFlowPosition]
  );

  const onDragOver = React.useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }, []);

  // Error highlight on nodes (fe-flow-edges)
  const displayNodes = React.useMemo(() => {
    if (!errorIdSets?.nodeIds.size) return nodes;
    return nodes.map((n) => {
      if (!errorIdSets.nodeIds.has(n.id)) return n;
      return { ...n, data: { ...n.data, hasError: true } };
    });
  }, [nodes, errorIdSets]);

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "calc(100vh - 160px)",
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius)",
        overflow: "hidden",
      }}
      onDrop={onDrop}
      onDragOver={onDragOver}
    >
      {/* Toolbar */}
      <div
        style={{
          position: "absolute",
          top: 12,
          left: 12,
          right: 12,
          display: "flex",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 8,
          zIndex: 5,
        }}
      >
        <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
          <Button
            size="sm"
            onClick={() => setShowPalette(true)}
            disabled={disabled}
            aria-label="Adicionar agente"
          >
            <Plus size={13} aria-hidden="true" />
            Agente
          </Button>
          <Button
            size="sm"
            onClick={handleUndo}
            disabled={disabled || historyIndex <= 0}
            aria-label="Desfazer"
          >
            <Undo2 size={13} aria-hidden="true" />
          </Button>
          <Button
            size="sm"
            onClick={handleRedo}
            disabled={disabled || historyIndex >= history.length - 1}
            aria-label="Refazer"
          >
            <Redo2 size={13} aria-hidden="true" />
          </Button>
          <Button
            size="sm"
            onClick={handleDeleteNode}
            disabled={disabled}
            aria-label="Excluir nó selecionado"
          >
            <Trash2 size={13} aria-hidden="true" />
          </Button>
          <div style={{ width: 1, height: 20, background: "var(--border)", margin: "0 4px" }} />
          <Button
            size="sm"
            onClick={() => zoomOut({ duration: 200 })}
            aria-label="Diminuir zoom"
          >
            <ZoomOut size={13} aria-hidden="true" />
          </Button>
          <Button
            size="sm"
            onClick={() => zoomIn({ duration: 200 })}
            aria-label="Aumentar zoom"
          >
            <ZoomIn size={13} aria-hidden="true" />
          </Button>
          <Button
            size="sm"
            onClick={() => fitView({ padding: 0.2, duration: 300 })}
            aria-label="Ajustar à tela"
          >
            <Maximize size={13} aria-hidden="true" />
          </Button>
        </div>

        <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
          {dirty && (
            <span
              style={{
                fontSize: 11,
                color: "var(--warning)",
                marginRight: 4,
              }}
            >
              Alterações não salvas
            </span>
          )}
          <Button
            size="sm"
            variant="primary"
            onClick={handleSave}
            disabled={disabled || !dirty || saving}
            aria-label="Salvar pipeline"
          >
            <Save size={13} aria-hidden="true" />
            {saving ? "Salvando..." : "Salvar"}
          </Button>
        </div>
      </div>

      {/* Legend */}
      <div
        style={{
          position: "absolute",
          bottom: 12,
          left: 12,
          background: "var(--bg-elevated)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-sm)",
          boxShadow: "var(--shadow)",
          padding: "6px 10px",
          zIndex: 5,
          display: "flex",
          gap: 12,
          fontSize: 11,
          color: "var(--text-muted)",
        }}
      >
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span
            style={{
              width: 16,
              height: 2,
              background: "var(--text-muted)",
              display: "inline-block",
            }}
          />
          Fluxo
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span
            style={{
              width: 16,
              height: 2,
              background: "repeating-linear-gradient(90deg, var(--text-muted) 0, var(--text-muted) 4px, transparent 4px, transparent 7px)",
              display: "inline-block",
            }}
          />
          Condição
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span
            style={{
              width: 16,
              height: 2,
              background: "repeating-linear-gradient(90deg, var(--info) 0, var(--info) 4px, transparent 4px, transparent 7px)",
              display: "inline-block",
            }}
          />
          Dados
        </span>
      </div>

      {/* React Flow canvas */}
      <ReactFlow
        nodes={displayNodes}
        edges={displayEdges}
        onNodesChange={onNodesChangeWrapper}
        onEdgesChange={onEdgesChangeWrapper}
        onConnect={onConnect}
        onSelectionChange={onSelectionChange}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        minZoom={0.1}
        maxZoom={2.0}
        deleteKeyCode={disabled ? null : ["Backspace", "Delete"]}
        nodesDraggable={!disabled}
        nodesConnectable={!disabled}
        elementsSelectable={!disabled}
        proOptions={{ hideAttribution: true }}
      >
        <Background
          gap={24}
          size={1}
          color="var(--border)"
        />
        <MiniMap
          nodeColor="var(--bg-hover)"
          maskColor="var(--bg)"
          style={{
            background: "var(--bg-elevated)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)",
          }}
        />
        {/* Arrow marker definition */}
        <defs>
          <marker
            id="arrowhead"
            viewBox="0 0 10 10"
            refX={10}
            refY={5}
            markerWidth={8}
            markerHeight={8}
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--text-muted)" />
          </marker>
        </defs>
      </ReactFlow>

      {/* Agent Palette */}
      {showPalette && (
        <AgentPalette
          agents={agents}
          onAddAgent={handleAddAgent}
          onClose={() => setShowPalette(false)}
        />
      )}

      {/* Edge Panel Slot (fe-flow-edges will plug in here) */}
      {edgePanelSlot && (
        <div
          style={{
            position: "absolute",
            top: 56,
            right: 12,
            zIndex: 10,
          }}
        >
          {edgePanelSlot}
        </div>
      )}
    </div>
  );
}

/**
 * Handle imperativo exposto pelo FlowEditor (E13: EdgePanel -> grafo interno).
 * A pagina chama `updateEdge` quando o EdgePanel altera uma aresta, para
 * sincronizar o estado interno do canvas com a edição.
 */
export interface FlowEditorHandle {
  /** Atualiza uma aresta no canvas (chamado pelo EdgePanel via pagina). */
  updateEdge: (edge: PipelineEdge) => void;
}

/**
 * FlowEditor: React Flow wrapper for pipeline editing.
 *
 * Public API:
 * - `pipeline`: the Pipeline to edit (nodes + edges)
 * - `agents`: available agents for the palette
 * - `onSave`: callback to persist nodes/edges (parent handles API call)
 * - `onEdgeSelect`: called when an edge is selected (null when deselected)
 * - `edgePanelSlot`: React node rendered in the right panel area (for fe-flow-edges)
 * - `disabled`: disables all interactions (e.g., during a run)
 * - `ref`: FlowEditorHandle com `updateEdge` para sincronizar o EdgePanel
 *
 * Extension point for fe-flow-edges:
 * - Pass `edgePanelSlot={<EdgePanel ... />}` to render the edge configuration panel
 * - Use `onEdgeSelect` to know which edge is selected
 * - Call `ref.current.updateEdge(edge)` to persist EdgePanel edits into the canvas
 */
export const FlowEditor = React.forwardRef<FlowEditorHandle, FlowEditorProps>(
  function FlowEditor(props, ref) {
    return (
      <ReactFlowProvider>
        <FlowEditorInner {...props} forwardedRef={ref} />
      </ReactFlowProvider>
    );
  }
);
