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
  type Node,
  type Edge,
  type NodeTypes,
  type EdgeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Play,
  Pause,
  Square,
  RotateCcw,
  ArrowLeft,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  Shield,
  Terminal,
  List,
  History,
  ZoomIn,
  ZoomOut,
  Maximize,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge, type BadgeStatus } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { Select } from "@/components/ui/select";
import { useToast } from "@/components/ui/toast";
import { AgentNode, type AgentNodeData } from "@/components/flow/agent-node";
import { PipelineEdgeComponent, type PipelineEdgeData } from "@/components/flow/pipeline-edge";
import { api, ApiError } from "@/lib/api";
import { RunInputsModal } from "@/components/flow/run-inputs-modal";
import { getWebSocketClient, disposeWebSocketClient } from "@/lib/websocket";
import type {
  Pipeline,
  PipelineRun,
  Checkpoint,
  PipelineStatusEvent,
  PipelineLogEvent,
  AgentOutputEvent,
  ApprovalNewEvent,
  ApprovalResolvedEvent,
} from "@/lib/types";

// ─── Types ───────────────────────────────────────────────────────────────────

export type NodeStatus = "pending" | "running" | "completed" | "failed" | "waiting_approval";

export interface LogEntry {
  id: string;
  nodeId: string;
  level: string;
  message: string;
  at: string;
}

export interface PipelineMonitorProps {
  pipelineId: string;
}

// ─── Status helpers ──────────────────────────────────────────────────────────

const NODE_STATUS_BADGE: Record<NodeStatus, BadgeStatus> = {
  pending: "pending",
  running: "running",
  completed: "completed",
  failed: "failed",
  waiting_approval: "warning",
};

const NODE_STATUS_LABEL: Record<NodeStatus, string> = {
  pending: "Pendente",
  running: "Executando",
  completed: "Concluído",
  failed: "Falhou",
  waiting_approval: "Aguardando aprovação",
};

const RUN_STATUS_BADGE: Record<PipelineRun["status"], BadgeStatus> = {
  running: "running",
  paused: "paused",
  completed: "completed",
  failed: "failed",
  cancelled: "cancelled",
};

const RUN_STATUS_LABEL: Record<PipelineRun["status"], string> = {
  running: "Executando",
  paused: "Pausado",
  completed: "Concluído",
  failed: "Falhou",
  cancelled: "Cancelado",
};

const LOG_LEVEL_COLORS: Record<string, string> = {
  debug: "var(--text-muted)",
  info: "var(--info)",
  warn: "var(--warning)",
  error: "var(--error)",
};

// ─── Conversion helpers (reuse from FlowEditor pattern) ─────────────────────

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

// ─── Node type registries ────────────────────────────────────────────────────

const nodeTypes: NodeTypes = {
  agent: AgentNode as unknown as NodeTypes["agent"],
};

const edgeTypes: EdgeTypes = {
  pipeline: PipelineEdgeComponent as unknown as EdgeTypes["pipeline"],
};

// ─── Inner monitor (needs ReactFlowProvider context) ─────────────────────────

function PipelineMonitorInner({ pipelineId }: PipelineMonitorProps) {
  const { addToast } = useToast();
  const { zoomIn, zoomOut, fitView } = useReactFlow();

  // ── Data state ──
  const [pipeline, setPipeline] = React.useState<Pipeline | null>(null);
  const [runs, setRuns] = React.useState<PipelineRun[]>([]);
  const [checkpoints, setCheckpoints] = React.useState<Checkpoint[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [notFound, setNotFound] = React.useState(false);

  // ── Real-time state ──
  const [nodeStatuses, setNodeStatuses] = React.useState<Record<string, NodeStatus>>({});
  const [logs, setLogs] = React.useState<LogEntry[]>([]);
  const [agentOutputs, setAgentOutputs] = React.useState<Record<string, unknown>>({});
  const [selectedNodeId, setSelectedNodeId] = React.useState<string | null>(null);
  const [activeRun, setActiveRun] = React.useState<PipelineRun | null>(null);

  // ── Log filters ──
  const [logNodeFilter, setLogNodeFilter] = React.useState<string>("all");
  const [logLevelFilter, setLogLevelFilter] = React.useState<string>("all");
  const [autoScroll, setAutoScroll] = React.useState(true);

  // ── Action states (optimistic) ──
  const [actionLoading, setActionLoading] = React.useState<string | null>(null);

  // ── React Flow state ──
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<AgentNodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge<PipelineEdgeData>>([]);

  // ── Refs ──
  const logContainerRef = React.useRef<HTMLDivElement>(null);
  const wsClientRef = React.useRef<ReturnType<typeof getWebSocketClient> | null>(null);

  // ── Fetch helpers ──
  const fetchAll = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const pipelineRes = await api.get<Pipeline>(`/api/pipelines/${pipelineId}`);
      setPipeline(pipelineRes);

      // Set initial node statuses from pipeline status
      const initialStatuses: Record<string, NodeStatus> = {};
      for (const node of pipelineRes.nodes) {
        if (pipelineRes.status === "completed") {
          initialStatuses[node.id] = "completed";
        } else {
          initialStatuses[node.id] = "pending";
        }
      }
      setNodeStatuses(initialStatuses);

      // Convert pipeline to flow nodes/edges
      setNodes(pipelineToFlowNodes(pipelineRes));
      setEdges(pipelineToFlowEdges(pipelineRes));

      // Fetch runs and checkpoints (non-blocking for initial render)
      try {
        const [runsRes, checkpointsRes] = await Promise.all([
          api.list<PipelineRun>(`/api/pipelines/${pipelineId}/runs`, { page: 1, limit: 50 }),
          api.list<Checkpoint>(`/api/pipelines/${pipelineId}/checkpoints`, { page: 1, limit: 50 }),
        ]);
        setRuns(runsRes.items);
        setCheckpoints(checkpointsRes.items);

        const sortedRuns = [...runsRes.items].sort(
          (a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime()
        );
        const latest = sortedRuns[0] ?? null;
        setActiveRun(latest);

        // Os eventos WS de nós que terminaram antes de o monitor abrir (ex.:
        // o 1º nó, logo após "Executar") não chegam de novo; os checkpoints
        // do run atual recompõem esse estado.
        if (latest) {
          const since = new Date(latest.startedAt).getTime();
          const fromCheckpoints: Record<string, NodeStatus> = {};
          for (const cp of checkpointsRes.items) {
            if (new Date(cp.timestamp).getTime() < since) continue;
            if (cp.status === "completed") fromCheckpoints[cp.nodeId] = "completed";
            else if (cp.status === "failed") fromCheckpoints[cp.nodeId] = "failed";
          }
          if (Object.keys(fromCheckpoints).length > 0) {
            setNodeStatuses((prev) => ({ ...prev, ...fromCheckpoints }));
          }
        }
      } catch {
        // Runs/checkpoints fetch failed: non-critical, monitor still works.
      }
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 404) {
          setNotFound(true);
        } else {
          setError(err.message);
        }
      } else {
        setError("Failed to load pipeline");
      }
    } finally {
      setLoading(false);
    }
  }, [pipelineId, setNodes, setEdges]);

  // ── Initial load ──
  React.useEffect(() => {
    void fetchAll();
  }, [fetchAll]);

  // ── WebSocket connection ──
  React.useEffect(() => {
    let onStatus: ((data: Record<string, unknown>) => void) | null = null;
    let onLog: ((data: Record<string, unknown>) => void) | null = null;
    let onOutput: ((data: Record<string, unknown>) => void) | null = null;
    let onApprovalNew: ((data: Record<string, unknown>) => void) | null = null;
    let onApprovalResolved: ((data: Record<string, unknown>) => void) | null = null;
    let onReconnect: (() => void) | null = null;

    const connect = async () => {
      try {
        const tokenRes = await fetch("/api/session-token", {
          method: "GET",
          credentials: "same-origin",
        });
        if (!tokenRes.ok) return;
        const { accessToken } = (await tokenRes.json()) as { accessToken: string };
        const client = getWebSocketClient(accessToken);
        wsClientRef.current = client;

        onStatus = (data: Record<string, unknown>) => {
          const event = data as unknown as PipelineStatusEvent;
          if (!event.pipelineId) return;
          if (!event.nodeId) {
            // Status agregado do run: atualiza o cabeçalho sem recarregar e,
            // no fim, busca o run de novo para trazer o motivo da falha.
            setActiveRun((prev) =>
              prev && (!event.runId || prev.id === event.runId)
                ? { ...prev, status: event.status as PipelineRun["status"] }
                : prev
            );
            if (event.status !== "running") void refreshRunsRef.current();
            return;
          }
          setNodeStatuses((prev) => ({
            ...prev,
            [event.nodeId]: event.status,
          }));
        };

        onLog = (data: Record<string, unknown>) => {
          const event = data as unknown as PipelineLogEvent;
          if (!event.pipelineId || !event.nodeId) return;
          const entry: LogEntry = {
            id: `log-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
            nodeId: event.nodeId,
            level: event.level,
            message: event.message,
            at: event.at,
          };
          setLogs((prev) => [...prev, entry]);
        };

        onOutput = (data: Record<string, unknown>) => {
          const event = data as unknown as AgentOutputEvent;
          if (!event.pipelineId || !event.nodeId) return;
          setAgentOutputs((prev) => ({
            ...prev,
            [event.nodeId]: event.output,
          }));
        };

        onApprovalNew = (data: Record<string, unknown>) => {
          const event = data as unknown as ApprovalNewEvent;
          if (!event.pipelineId || !event.nodeId) return;
          setNodeStatuses((prev) => ({
            ...prev,
            [event.nodeId]: "waiting_approval",
          }));
        };

        onApprovalResolved = (data: Record<string, unknown>) => {
          const event = data as unknown as ApprovalResolvedEvent;
          if (!event.pipelineId || !event.nodeId) return;
          const newStatus: NodeStatus =
            event.decision === "approved" ? "running" : "failed";
          setNodeStatuses((prev) => ({
            ...prev,
            [event.nodeId]: newStatus,
          }));
        };

        onReconnect = () => {
          void fetchAll();
        };

        client.on("pipeline:status", onStatus, pipelineId);
        client.on("pipeline:log", onLog, pipelineId);
        client.on("agent:output", onOutput, pipelineId);
        client.on("approval:new", onApprovalNew, pipelineId);
        client.on("approval:resolved", onApprovalResolved, pipelineId);
        client.onReconnect(onReconnect);
        client.connect();
      } catch {
        // WS unavailable: monitor continues with REST (manual refresh).
      }
    };

    void connect();

    return () => {
      const client = wsClientRef.current;
      if (client) {
        if (onStatus) client.off("pipeline:status", onStatus, pipelineId);
        if (onLog) client.off("pipeline:log", onLog, pipelineId);
        if (onOutput) client.off("agent:output", onOutput, pipelineId);
        if (onApprovalNew) client.off("approval:new", onApprovalNew, pipelineId);
        if (onApprovalResolved) client.off("approval:resolved", onApprovalResolved, pipelineId);
      }
      disposeWebSocketClient();
      wsClientRef.current = null;
    };
  }, [pipelineId, fetchAll]);

  // ── Auto-scroll logs ──
  React.useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  // ── Filtered logs ──
  const filteredLogs = React.useMemo(() => {
    return logs.filter((log) => {
      if (logNodeFilter !== "all" && log.nodeId !== logNodeFilter) return false;
      if (logLevelFilter !== "all" && log.level !== logLevelFilter) return false;
      return true;
    });
  }, [logs, logNodeFilter, logLevelFilter]);

  // ── Node options for log filter ──
  const nodeOptions = React.useMemo(() => {
    if (!pipeline) return [];
    return pipeline.nodes.map((n) => ({
      value: n.id,
      label: n.label ?? n.agentSnapshot.name,
    }));
  }, [pipeline]);

  const refreshRuns = React.useCallback(async () => {
    try {
      const runsRes = await api.list<PipelineRun>(`/api/pipelines/${pipelineId}/runs`, { page: 1, limit: 50 });
      setRuns(runsRes.items);
      const sorted = [...runsRes.items].sort(
        (a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime()
      );
      setActiveRun(sorted[0] ?? null);
    } catch {
      // Não crítico: o cabeçalho já foi atualizado pelo evento WS.
    }
  }, [pipelineId]);
  const refreshRunsRef = React.useRef(refreshRuns);
  refreshRunsRef.current = refreshRuns;

  // ── Action handlers ──
  const [runInputsOpen, setRunInputsOpen] = React.useState(false);
  const entryNode = pipeline
    ? pipeline.nodes.find((n) => n.id === pipeline.entryNodeId) ?? pipeline.nodes[0]
    : undefined;

  const handleExecute = React.useCallback(async (runInputs: Record<string, string> = {}) => {
    setActionLoading("execute");
    try {
      await api.post(`/api/pipelines/${pipelineId}/execute`, { inputs: runInputs });
      setRunInputsOpen(false);
      addToast("success", "Pipeline iniciada.");
      // Optimistic: set all nodes to pending
      setNodeStatuses((prev) => {
        const next = { ...prev };
        for (const key of Object.keys(next)) {
          next[key] = "pending";
        }
        return next;
      });
      // Refetch runs to get the new run
      const runsRes = await api.list<PipelineRun>(`/api/pipelines/${pipelineId}/runs`, { page: 1, limit: 50 });
      setRuns(runsRes.items);
      const sortedRuns = [...runsRes.items].sort(
        (a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime()
      );
      setActiveRun(sortedRuns[0] ?? null);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          addToast("warning", "Pipeline já está em execução.");
        } else {
          addToast("error", err.message);
        }
      } else {
        addToast("error", "Falha ao iniciar a pipeline.");
      }
    } finally {
      setActionLoading(null);
    }
  }, [pipelineId, addToast]);

  const handlePause = React.useCallback(async () => {
    setActionLoading("pause");
    try {
      await api.post(`/api/pipelines/${pipelineId}/pause`, {});
      addToast("info", "Pipeline pausada.");
      if (activeRun) {
        setActiveRun({ ...activeRun, status: "paused" });
      }
    } catch (err) {
      if (err instanceof ApiError) {
        addToast("error", err.message);
      } else {
        addToast("error", "Falha ao pausar a pipeline.");
      }
    } finally {
      setActionLoading(null);
    }
  }, [pipelineId, activeRun, addToast]);

  const handleResume = React.useCallback(async () => {
    setActionLoading("resume");
    try {
      await api.post(`/api/pipelines/${pipelineId}/resume`, {});
      addToast("info", "Pipeline retomada.");
      if (activeRun) {
        setActiveRun({ ...activeRun, status: "running" });
      }
    } catch (err) {
      if (err instanceof ApiError) {
        addToast("error", err.message);
      } else {
        addToast("error", "Falha ao retomar a pipeline.");
      }
    } finally {
      setActionLoading(null);
    }
  }, [pipelineId, activeRun, addToast]);

  const handleStop = React.useCallback(async () => {
    setActionLoading("stop");
    try {
      await api.post(`/api/pipelines/${pipelineId}/stop`, {});
      addToast("info", "Pipeline parada.");
      if (activeRun) {
        setActiveRun({ ...activeRun, status: "cancelled" });
      }
    } catch (err) {
      if (err instanceof ApiError) {
        addToast("error", err.message);
      } else {
        addToast("error", "Falha ao parar a pipeline.");
      }
    } finally {
      setActionLoading(null);
    }
  }, [pipelineId, activeRun, addToast]);

  const handleResumeFromCheckpoint = React.useCallback(
    async (checkpointId: string) => {
      setActionLoading(`resume-cp-${checkpointId}`);
      try {
        await api.post(`/api/pipelines/${pipelineId}/checkpoints/${checkpointId}/resume`, {});
        addToast("info", "Pipeline retomada do checkpoint.");
        if (activeRun) {
          setActiveRun({ ...activeRun, status: "running" });
        }
      } catch (err) {
        if (err instanceof ApiError) {
          addToast("error", err.message);
        } else {
          addToast("error", "Falha ao retomar do checkpoint.");
        }
      } finally {
        setActionLoading(null);
      }
    },
    [pipelineId, activeRun, addToast]
  );

  // ── Node click handler ──
  const onNodeClick = React.useCallback(
    (_: React.MouseEvent, node: Node<AgentNodeData>) => {
      setSelectedNodeId(node.id);
    },
    []
  );

  // ── Selected node data ──
  const selectedNode = React.useMemo(() => {
    if (!selectedNodeId || !pipeline) return null;
    return pipeline.nodes.find((n) => n.id === selectedNodeId) ?? null;
  }, [selectedNodeId, pipeline]);

  const selectedNodeStatus = selectedNodeId ? nodeStatuses[selectedNodeId] : undefined;
  const selectedNodeOutput = selectedNodeId ? agentOutputs[selectedNodeId] : undefined;

  // ── Loading state ──
  if (loading) {
    return (
      <div>
        <div style={{ marginBottom: 16 }}>
          <Skeleton height={32} width={200} />
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 320px",
            gap: 16,
            height: "calc(100vh - 200px)",
          }}
        >
          <Skeleton height="100%" />
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <Skeleton height={120} />
            <Skeleton height="100%" />
          </div>
        </div>
      </div>
    );
  }

  // ── Not found ──
  if (notFound) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="Pipeline não encontrada"
        description="Esta pipeline não existe ou foi excluída."
      />
    );
  }

  // ── Error state ──
  if (error) {
    return (
      <div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            padding: "16px 20px",
            background: "var(--bg-elevated)",
            border: "1px solid var(--error)",
            borderRadius: "var(--radius)",
            marginBottom: 16,
          }}
        >
          <AlertTriangle size={18} style={{ color: "var(--error)" }} aria-hidden="true" />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>
              Falha ao carregar o monitor
            </div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{error}</div>
          </div>
          <Button size="sm" onClick={() => void fetchAll()} aria-label="Tentar novamente">
            <RefreshCw size={12} aria-hidden="true" />
            Tentar novamente
          </Button>
        </div>
      </div>
    );
  }

  if (!pipeline) return null;

  const isRunning = activeRun?.status === "running";
  const isPaused = activeRun?.status === "paused";
  const isTerminal =
    activeRun?.status === "completed" ||
    activeRun?.status === "failed" ||
    activeRun?.status === "cancelled";

  const canExecute = !isRunning && !isPaused;
  const canPause = isRunning;
  const canResume = isPaused;
  const canStop = isRunning || isPaused;

  return (
    <div>
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          marginBottom: 16,
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Button
            size="sm"
            onClick={() => window.history.back()}
            aria-label="Voltar"
          >
            <ArrowLeft size={14} aria-hidden="true" />
          </Button>
          <div>
            <h1
              style={{
                fontSize: "var(--text-title)",
                fontWeight: 700,
                color: "var(--text)",
                margin: 0,
              }}
            >
              {pipeline.name}
            </h1>
            {activeRun && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
                <Badge
                  status={RUN_STATUS_BADGE[activeRun.status]}
                  label={RUN_STATUS_LABEL[activeRun.status]}
                  pulse={activeRun.status === "running"}
                />
                <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                  Iniciado: {new Date(activeRun.startedAt).toLocaleString("pt-BR")}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Action buttons */}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {canExecute && (
            <Button
              size="sm"
              variant="primary"
              onClick={() => {
                if (entryNode && entryNode.agentSnapshot.inputs.length > 0) setRunInputsOpen(true);
                else void handleExecute();
              }}
              loading={actionLoading === "execute"}
              aria-label="Iniciar execução"
            >
              <Play size={13} aria-hidden="true" />
              Iniciar
            </Button>
          )}
          {canPause && (
            <Button
              size="sm"
              onClick={() => void handlePause()}
              loading={actionLoading === "pause"}
              aria-label="Pausar"
            >
              <Pause size={13} aria-hidden="true" />
              Pausar
            </Button>
          )}
          {canResume && (
            <Button
              size="sm"
              variant="primary"
              onClick={() => void handleResume()}
              loading={actionLoading === "resume"}
              aria-label="Retomar"
            >
              <Play size={13} aria-hidden="true" />
              Retomar
            </Button>
          )}
          {canStop && (
            <Button
              size="sm"
              onClick={() => void handleStop()}
              loading={actionLoading === "stop"}
              style={{ color: "var(--error)" }}
              aria-label="Parar"
            >
              <Square size={13} aria-hidden="true" />
              Parar
            </Button>
          )}
          <Button
            size="sm"
            onClick={() => void fetchAll()}
            aria-label="Atualizar"
          >
            <RefreshCw size={13} aria-hidden="true" />
          </Button>
        </div>
      </div>

      {activeRun?.status === "failed" && activeRun.error && (
        <div
          role="alert"
          style={{
            display: "flex",
            gap: 8,
            alignItems: "flex-start",
            padding: "10px 14px",
            marginBottom: 12,
            borderRadius: "var(--radius)",
            border: "1px solid var(--error)",
            background: "var(--error-bg)",
            color: "var(--text)",
            fontSize: 12,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          <strong style={{ color: "var(--error)", flexShrink: 0 }}>Falha na execução:</strong>
          <span>{activeRun.error}</span>
        </div>
      )}

      {entryNode && (
        <RunInputsModal
          open={runInputsOpen}
          agentName={entryNode.agentSnapshot.name}
          inputs={entryNode.agentSnapshot.inputs}
          busy={actionLoading === "execute"}
          onCancel={() => setRunInputsOpen(false)}
          onSubmit={(values) => void handleExecute(values)}
        />
      )}

      {/* Main grid: graph + right panel */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 320px",
          gap: 16,
          height: "calc(100vh - 200px)",
        }}
      >
        {/* Left: Graph */}
        <div
          style={{
            position: "relative",
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
            overflow: "hidden",
          }}
        >
          {/* Toolbar */}
          <div
            style={{
              position: "absolute",
              top: 12,
              left: 12,
              display: "flex",
              gap: 4,
              zIndex: 5,
            }}
          >
            <Button
              size="sm"
              onClick={() => zoomOut({ duration: 200 })}
              aria-label="Zoom out"
            >
              <ZoomOut size={13} aria-hidden="true" />
            </Button>
            <Button
              size="sm"
              onClick={() => zoomIn({ duration: 200 })}
              aria-label="Zoom in"
            >
              <ZoomIn size={13} aria-hidden="true" />
            </Button>
            <Button
              size="sm"
              onClick={() => fitView({ padding: 0.2, duration: 300 })}
              aria-label="Fit to view"
            >
              <Maximize size={13} aria-hidden="true" />
            </Button>
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
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: "var(--warning)",
                  display: "inline-block",
                }}
              />
              Pendente
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: "var(--info)",
                  display: "inline-block",
                }}
              />
              Executando
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: "var(--success)",
                  display: "inline-block",
                }}
              />
              Concluído
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: "var(--error)",
                  display: "inline-block",
                }}
              />
              Falhou
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: "var(--warning)",
                  display: "inline-block",
                }}
              />
              Aprovação
            </span>
          </div>

          {/* React Flow canvas (read-only) */}
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            fitView
            fitViewOptions={{ padding: 0.3 }}
            minZoom={0.1}
            maxZoom={2.0}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={true}
            deleteKeyCode={null}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={24} size={1} color="var(--border)" />
            <MiniMap
              nodeColor="var(--bg-hover)"
              maskColor="var(--bg)"
              style={{
                background: "var(--bg-elevated)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
              }}
            />
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
        </div>

        {/* Right panel: tabs for Node / Logs / History */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 12,
            overflow: "hidden",
          }}
        >
          {/* Node panel */}
          <Card style={{ flexShrink: 0 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 10,
              }}
            >
              <Terminal size={14} aria-hidden="true" style={{ color: "var(--text-muted)" }} />
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: "var(--text-secondary)",
                  textTransform: "uppercase",
                  letterSpacing: "0.5px",
                }}
              >
                Nó selecionado
              </span>
            </div>

            {!selectedNode ? (
              <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0 }}>
                Clique em um nó no grafo para ver detalhes.
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {/* Node name + status */}
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>
                    {selectedNode.label ?? selectedNode.agentSnapshot.name}
                  </span>
                  {selectedNodeStatus && (
                    <Badge
                      status={NODE_STATUS_BADGE[selectedNodeStatus]}
                      label={NODE_STATUS_LABEL[selectedNodeStatus]}
                      pulse={selectedNodeStatus === "running"}
                    />
                  )}
                </div>

                {/* Inputs */}
                {selectedNode.agentSnapshot.inputs.length > 0 && (
                  <div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>
                      Entradas
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                      {selectedNode.agentSnapshot.inputs.map((port) => (
                        <span
                          key={port.name}
                          style={{
                            fontSize: 11,
                            color: "var(--text)",
                            background: "var(--bg-hover)",
                            border: "1px solid var(--border-subtle)",
                            borderRadius: 10,
                            padding: "1px 8px",
                          }}
                        >
                          {port.name}
                          {port.required && (
                            <span style={{ color: "var(--error)", marginLeft: 2 }}>*</span>
                          )}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Outputs */}
                {selectedNode.agentSnapshot.outputs.length > 0 && (
                  <div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>
                      Saídas
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                      {selectedNode.agentSnapshot.outputs.map((port) => (
                        <span
                          key={port.name}
                          style={{
                            fontSize: 11,
                            color: "var(--text)",
                            background: "var(--bg-hover)",
                            border: "1px solid var(--border-subtle)",
                            borderRadius: 10,
                            padding: "1px 8px",
                          }}
                        >
                          {port.name}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Iterations */}
                <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                  Max iterações: {selectedNode.agentSnapshot.maxIterations}
                </div>

                {/* Output (from agent:output WS) */}
                {selectedNodeOutput !== undefined && (
                  <div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>
                      Último output
                    </div>
                    <pre
                      style={{
                        fontSize: 11,
                        color: "var(--text)",
                        background: "var(--bg-elevated)",
                        border: "1px solid var(--border)",
                        borderRadius: "var(--radius-sm)",
                        padding: 8,
                        overflow: "auto",
                        maxHeight: 120,
                        margin: 0,
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word",
                      }}
                    >
                      {typeof selectedNodeOutput === "string"
                        ? selectedNodeOutput
                        : JSON.stringify(selectedNodeOutput, null, 2)}
                    </pre>
                  </div>
                )}

                {/* Error (from logs) */}
                {selectedNodeStatus === "failed" && (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: 6,
                      padding: 8,
                      background: "rgba(248, 113, 113, 0.1)",
                      border: "1px solid var(--error)",
                      borderRadius: "var(--radius-sm)",
                    }}
                  >
                    <XCircle size={14} style={{ color: "var(--error)", flexShrink: 0, marginTop: 1 }} aria-hidden="true" />
                    <span style={{ fontSize: 12, color: "var(--error)" }}>
                      Este nó falhou. Verifique os logs para detalhes.
                    </span>
                  </div>
                )}

                {/* Waiting approval */}
                {selectedNodeStatus === "waiting_approval" && (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      padding: 8,
                      background: "var(--accent-subtle)",
                      border: "1px solid var(--accent)",
                      borderRadius: "var(--radius-sm)",
                    }}
                  >
                    <Shield size={14} style={{ color: "var(--accent)", flexShrink: 0 }} aria-hidden="true" />
                    <span style={{ fontSize: 12, color: "var(--text)" }}>
                      Aguardando aprovação humana.
                    </span>
                  </div>
                )}
              </div>
            )}
          </Card>

          {/* Logs panel */}
          <Card style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: 8,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <List size={14} aria-hidden="true" style={{ color: "var(--text-muted)" }} />
                <span
                  style={{
                    fontSize: 12,
                    fontWeight: 600,
                    color: "var(--text-secondary)",
                    textTransform: "uppercase",
                    letterSpacing: "0.5px",
                  }}
                >
                  Logs
                </span>
              </div>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <button
                  onClick={() => setAutoScroll(!autoScroll)}
                  aria-label={autoScroll ? "Desativar auto-scroll" : "Ativar auto-scroll"}
                  aria-pressed={autoScroll}
                  style={{
                    background: "none",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-sm)",
                    padding: "4px 8px",
                    fontSize: 11,
                    color: autoScroll ? "var(--accent)" : "var(--text-muted)",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: 4,
                  }}
                >
                  <span style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase" }}>
                    Auto
                  </span>
                </button>
              </div>
            </div>

            {/* Filters */}
            <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
              <div style={{ flex: 1 }}>
                <Select
                  aria-label="Filtrar por nó"
                  value={logNodeFilter}
                  onValueChange={setLogNodeFilter}
                  options={[
                    { value: "all", label: "Todos os nós" },
                    ...nodeOptions,
                  ]}
                />
              </div>
              <div style={{ flex: 1 }}>
                <Select
                  aria-label="Filtrar por nível"
                  value={logLevelFilter}
                  onValueChange={setLogLevelFilter}
                  options={[
                    { value: "all", label: "Todos os níveis" },
                    { value: "debug", label: "Debug" },
                    { value: "info", label: "Info" },
                    { value: "warn", label: "Warn" },
                    { value: "error", label: "Error" },
                  ]}
                />
              </div>
            </div>

            {/* Log entries */}
            <div
              ref={logContainerRef}
              role="log"
              aria-label="Logs da execução"
              style={{
                flex: 1,
                overflowY: "auto",
                background: "var(--bg-elevated)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
                padding: 8,
                fontFamily: "var(--font-mono)",
                fontSize: 11,
                lineHeight: 1.6,
              }}
            >
              {filteredLogs.length === 0 ? (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    height: "100%",
                    color: "var(--text-muted)",
                    fontSize: 12,
                  }}
                >
                  {logs.length === 0
                    ? "Aguardando logs da execução…"
                    : "Nenhum log corresponde ao filtro."}
                </div>
              ) : (
                filteredLogs.map((log) => (
                  <div
                    key={log.id}
                    style={{
                      display: "flex",
                      gap: 6,
                      padding: "2px 0",
                      borderBottom: "1px solid var(--border-subtle)",
                    }}
                  >
                    <span
                      style={{
                        color: "var(--text-muted)",
                        flexShrink: 0,
                        whiteSpace: "nowrap",
                      }}
                    >
                      {new Date(log.at).toLocaleTimeString("pt-BR")}
                    </span>
                    <span
                      style={{
                        color: LOG_LEVEL_COLORS[log.level] ?? "var(--text-secondary)",
                        fontWeight: 600,
                        flexShrink: 0,
                        textTransform: "uppercase",
                        fontSize: 10,
                        minWidth: 40,
                      }}
                    >
                      {log.level}
                    </span>
                    <span
                      style={{
                        color: "var(--text-muted)",
                        flexShrink: 0,
                        maxWidth: 80,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                      title={log.nodeId}
                    >
                      {log.nodeId}
                    </span>
                    <span style={{ color: "var(--text)", wordBreak: "break-word" }}>
                      {log.message}
                    </span>
                  </div>
                ))
              )}
            </div>
          </Card>

          {/* History panel */}
          <Card style={{ flexShrink: 0, maxHeight: 200, overflow: "hidden", display: "flex", flexDirection: "column" }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 8,
              }}
            >
              <History size={14} aria-hidden="true" style={{ color: "var(--text-muted)" }} />
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: "var(--text-secondary)",
                  textTransform: "uppercase",
                  letterSpacing: "0.5px",
                }}
              >
                Histórico
              </span>
            </div>

            <div style={{ overflowY: "auto", flex: 1 }}>
              {runs.length === 0 ? (
                <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0 }}>
                  Nenhuma execução ainda.
                </p>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {runs.map((run) => (
                    <div
                      key={run.id}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: 8,
                        padding: "6px 8px",
                        background: "var(--bg-elevated)",
                        border: "1px solid var(--border)",
                        borderRadius: "var(--radius-sm)",
                      }}
                    >
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ fontSize: 11, color: "var(--text)", fontWeight: 500 }}>
                          {new Date(run.startedAt).toLocaleString("pt-BR")}
                        </div>
                        {run.error && (
                          <div
                            style={{
                              fontSize: 10,
                              color: "var(--error)",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {run.error}
                          </div>
                        )}
                      </div>
                      <Badge
                        status={RUN_STATUS_BADGE[run.status]}
                        label={RUN_STATUS_LABEL[run.status]}
                      />
                    </div>
                  ))}
                </div>
              )}

              {/* Checkpoints */}
              {checkpoints.length > 0 && (
                <div style={{ marginTop: 10 }}>
                  <div
                    style={{
                      fontSize: 11,
                      color: "var(--text-muted)",
                      marginBottom: 6,
                      display: "flex",
                      alignItems: "center",
                      gap: 4,
                    }}
                  >
                    <Clock size={11} aria-hidden="true" />
                    Checkpoints
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    {checkpoints.map((cp) => (
                      <div
                        key={cp.id}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          gap: 8,
                          padding: "4px 8px",
                          background: "var(--bg-elevated)",
                          border: "1px solid var(--border-subtle)",
                          borderRadius: "var(--radius-sm)",
                        }}
                      >
                        <div style={{ minWidth: 0, flex: 1 }}>
                          <div style={{ fontSize: 11, color: "var(--text)" }}>
                            {new Date(cp.timestamp).toLocaleString("pt-BR")}
                          </div>
                          <div style={{ fontSize: 10, color: "var(--text-muted)" }}>
                            Nó: {cp.nodeId}
                          </div>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <Badge
                            status={
                              cp.status === "completed"
                                ? "completed"
                                : cp.status === "interrupted"
                                  ? "paused"
                                  : "failed"
                            }
                            label={
                              cp.status === "completed"
                                ? "Concluído"
                                : cp.status === "interrupted"
                                  ? "Interrompido"
                                  : "Falhou"
                            }
                          />
                          {(cp.status === "interrupted" || cp.status === "failed") && (
                            <Button
                              size="sm"
                              onClick={() => void handleResumeFromCheckpoint(cp.id)}
                              loading={actionLoading === `resume-cp-${cp.id}`}
                              aria-label={`Retomar do checkpoint ${cp.id}`}
                            >
                              <RotateCcw size={11} aria-hidden="true" />
                              Retomar
                            </Button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

/**
 * PipelineMonitor: real-time pipeline execution monitor.
 *
 * - Read-only graph with per-node status (pending, running, completed, failed, waiting_approval).
 * - Streaming logs with auto-scroll (pausable), filter by node and level.
 * - Selected node panel: inputs, outputs, iterations, error, last output.
 * - Actions: execute, pause, resume, stop (optimistic + server reconciliation).
 * - Run history and checkpoints with resume from checkpoint.
 * - WebSocket reconnection: refetch REST state on reconnect.
 *
 * Endpoints:
 * - GET  /api/pipelines/{id}
 * - GET  /api/pipelines/{id}/runs
 * - GET  /api/pipelines/{id}/checkpoints
 * - POST /api/pipelines/{id}/execute
 * - POST /api/pipelines/{id}/pause
 * - POST /api/pipelines/{id}/resume
 * - POST /api/pipelines/{id}/stop
 * - POST /api/pipelines/{id}/checkpoints/{cpId}/resume
 *
 * WS channels (filtered by pipelineId):
 * - pipeline:status
 * - pipeline:log
 * - agent:output
 * - approval:new
 * - approval:resolved
 */
export function PipelineMonitor(props: PipelineMonitorProps) {
  return (
    <ReactFlowProvider>
      <PipelineMonitorInner {...props} />
    </ReactFlowProvider>
  );
}
