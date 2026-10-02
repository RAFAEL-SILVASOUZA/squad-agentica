"use client";

import * as React from "react";
import { ReactFlowProvider } from "@xyflow/react";
import { Play, Pause, Square, RefreshCw, AlertTriangle, Network } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { Modal } from "@/components/ui/modal";
import { Tabs, type TabItem } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
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
import type { NodeStatus } from "./status";
import type { LogEntry } from "./logs-tab";
import { RunHeader } from "./run-header";
import { StageStrip, buildStages } from "./stage-strip";
import { ResultsTab } from "./results-tab";
import { FilesTab } from "./files-tab";
import { LogsTab } from "./logs-tab";
import { HistoryTab } from "./history-tab";
import { RunGraph } from "./run-graph";
import { buildTimeline, type TimelineEvent } from "./timeline";

export type { NodeStatus } from "./status";
export type { LogEntry } from "./logs-tab";

export interface PipelineMonitorProps {
  pipelineId: string;
}

// ─── Abas (a ativa fica em ?tab=) ────────────────────────────────────────────

export type MonitorTab = "resultado" | "arquivos" | "logs" | "historico";

const TAB_IDS: MonitorTab[] = ["resultado", "arquivos", "logs", "historico"];

function tabFromUrl(): MonitorTab {
  if (typeof window === "undefined") return "resultado";
  const tab = new URLSearchParams(window.location.search).get("tab");
  return TAB_IDS.includes(tab as MonitorTab) ? (tab as MonitorTab) : "resultado";
}

function writeTabToUrl(tab: MonitorTab) {
  const url = new URL(window.location.href);
  url.searchParams.set("tab", tab);
  // Mantém o state do histórico (o App Router guarda o dele ali).
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
}

function latestRun(runs: PipelineRun[]): PipelineRun | null {
  const sorted = [...runs].sort((a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime());
  return sorted[0] ?? null;
}

// ─── Contêiner: estado, WebSocket e abas ─────────────────────────────────────

function PipelineMonitorInner({ pipelineId }: PipelineMonitorProps) {
  const { addToast } = useToast();

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
  const [activeRun, setActiveRun] = React.useState<PipelineRun | null>(null);
  const [statusEvents, setStatusEvents] = React.useState<TimelineEvent[]>([]);
  const [changedFilesCount, setChangedFilesCount] = React.useState(0);

  // ── UI state ──
  const [activeTab, setActiveTab] = React.useState<MonitorTab>(tabFromUrl);
  const [focus, setFocus] = React.useState<{ nodeId: string; key: number } | null>(null);
  const [graphOpen, setGraphOpen] = React.useState(false);
  const [actionLoading, setActionLoading] = React.useState<string | null>(null);
  const [publishing, setPublishing] = React.useState(false);
  const [runInputsOpen, setRunInputsOpen] = React.useState(false);
  // Recarrega a lista de arquivos do run (nó concluído / status do run).
  const [filesVersion, setFilesVersion] = React.useState(0);

  const wsClientRef = React.useRef<ReturnType<typeof getWebSocketClient> | null>(null);

  const changeTab = React.useCallback((tab: MonitorTab) => {
    setActiveTab(tab);
    writeTabToUrl(tab);
  }, []);

  // ── Fetch helpers ──
  const fetchAll = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const pipelineRes = await api.get<Pipeline>(`/api/pipelines/${pipelineId}`);
      setPipeline(pipelineRes);

      const initialStatuses: Record<string, NodeStatus> = {};
      for (const node of pipelineRes.nodes) {
        initialStatuses[node.id] = pipelineRes.status === "completed" ? "completed" : "pending";
      }
      setNodeStatuses(initialStatuses);

      try {
        const [runsRes, checkpointsRes] = await Promise.all([
          api.list<PipelineRun>(`/api/pipelines/${pipelineId}/runs`, { page: 1, limit: 50 }),
          api.list<Checkpoint>(`/api/pipelines/${pipelineId}/checkpoints`, { page: 1, limit: 50 }),
        ]);
        setRuns(runsRes.items);
        setCheckpoints(checkpointsRes.items);

        const latest = latestRun(runsRes.items);
        setActiveRun(latest);

        // Os eventos WS de nós que terminaram antes de o monitor abrir (ex.:
        // o 1º nó, logo após "Executar") não chegam de novo; os checkpoints
        // do run atual recompõem esse estado.
        if (latest) {
          const since = new Date(latest.startedAt).getTime();
          const fromCheckpoints: Record<string, NodeStatus> = {};
          const outputsFromCheckpoints: Record<string, unknown> = {};
          for (const cp of checkpointsRes.items) {
            if (new Date(cp.timestamp).getTime() < since) continue;
            if (cp.status === "completed") fromCheckpoints[cp.nodeId] = "completed";
            else if (cp.status === "failed") fromCheckpoints[cp.nodeId] = "failed";
            // A saída do nó também fica no checkpoint: ao reabrir o monitor
            // a aba Resultado volta a mostrá-la (o agent:output já passou).
            const data = (cp.state as { data?: Record<string, unknown> } | undefined)?.data;
            if (data && data[cp.nodeId] !== undefined) outputsFromCheckpoints[cp.nodeId] = data[cp.nodeId];
          }
          if (Object.keys(fromCheckpoints).length > 0) {
            setNodeStatuses((prev) => ({ ...prev, ...fromCheckpoints }));
          }
          if (Object.keys(outputsFromCheckpoints).length > 0) {
            setAgentOutputs((prev) => ({ ...outputsFromCheckpoints, ...prev }));
          }
        }
      } catch {
        // Runs/checkpoints fetch failed: non-critical, monitor still works.
      }
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 404) setNotFound(true);
        else setError(err.message);
      } else {
        setError("Falha ao carregar a pipeline.");
      }
    } finally {
      setLoading(false);
    }
  }, [pipelineId]);

  React.useEffect(() => {
    void fetchAll();
  }, [fetchAll]);

  const refreshRuns = React.useCallback(async () => {
    try {
      const runsRes = await api.list<PipelineRun>(`/api/pipelines/${pipelineId}/runs`, { page: 1, limit: 50 });
      setRuns(runsRes.items);
      setActiveRun(latestRun(runsRes.items));
    } catch {
      // Não crítico: o cabeçalho já foi atualizado pelo evento WS.
    }
  }, [pipelineId]);
  const refreshRunsRef = React.useRef(refreshRuns);
  refreshRunsRef.current = refreshRuns;

  // Contagem de arquivos alterados (para a aba): busca independente da aba estar aberta.
  const fetchChangedCount = React.useCallback(async (runId: string) => {
    try {
      const res = await api.get<{ items: { status: string | null }[] }>(`/api/runs/${runId}/files`);
      setChangedFilesCount(res.items.filter((f) => f.status).length);
    } catch {
      // Não crítico.
    }
  }, []);

  React.useEffect(() => {
    if (activeRun) void fetchChangedCount(activeRun.id);
    else setChangedFilesCount(0);
  }, [activeRun, filesVersion, fetchChangedCount]);

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
            // Status agregado do run: atualiza o cabeçalho na hora e sempre
            // recarrega o run — traz o motivo da falha e, no 2º "completed"
            // (emitido quando a publicação termina), o link do PR.
            setActiveRun((prev) =>
              prev && (!event.runId || prev.id === event.runId)
                ? { ...prev, status: event.status as PipelineRun["status"] }
                : prev
            );
            void refreshRunsRef.current();
            setFilesVersion((v) => v + 1);
            return;
          }
          setNodeStatuses((prev) => ({ ...prev, [event.nodeId]: event.status }));
          // Registra o evento para a linha do tempo.
          setStatusEvents((prev) => [...prev, { nodeId: event.nodeId, status: event.status, at: event.at }]);
          // Um agente terminou: pode ter escrito no workspace.
          if (event.status === "completed") setFilesVersion((v) => v + 1);
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
          setAgentOutputs((prev) => ({ ...prev, [event.nodeId]: event.output }));
        };

        onApprovalNew = (data: Record<string, unknown>) => {
          const event = data as unknown as ApprovalNewEvent;
          if (!event.pipelineId || !event.nodeId) return;
          setNodeStatuses((prev) => ({ ...prev, [event.nodeId]: "waiting_approval" }));
        };

        onApprovalResolved = (data: Record<string, unknown>) => {
          const event = data as unknown as ApprovalResolvedEvent;
          if (!event.pipelineId || !event.nodeId) return;
          const newStatus: NodeStatus = event.decision === "approved" ? "running" : "failed";
          setNodeStatuses((prev) => ({ ...prev, [event.nodeId]: newStatus }));
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

  // ── Derived data ──
  const stages = React.useMemo(
    () => (pipeline ? buildStages(pipeline, nodeStatuses) : []),
    [pipeline, nodeStatuses]
  );
  const resultSteps = React.useMemo(
    () =>
      stages
        .filter((s) => s.kind === "agent")
        .map((s) => ({ nodeId: s.nodeId, name: s.name, status: s.status, output: agentOutputs[s.nodeId] })),
    [stages, agentOutputs]
  );
  const agents = React.useMemo(() => resultSteps.map((s) => ({ nodeId: s.nodeId, name: s.name })), [resultSteps]);

  // Linha do tempo por nó (eventos WS + checkpoints do run atual).
  const timeline = React.useMemo(() => {
    const cps = activeRun
      ? checkpoints
          .filter((cp) => new Date(cp.timestamp).getTime() >= new Date(activeRun.startedAt).getTime())
          .map((cp) => ({ nodeId: cp.nodeId, timestamp: cp.timestamp, status: cp.status }))
      : [];
    return buildTimeline(statusEvents, cps);
  }, [statusEvents, checkpoints, activeRun]);

  const hasErrorLogs = React.useMemo(() => logs.some((l) => l.level === "error"), [logs]);

  const focusResult = React.useCallback(
    (nodeId: string) => {
      changeTab("resultado");
      setFocus((prev) => ({ nodeId, key: (prev?.key ?? 0) + 1 }));
    },
    [changeTab]
  );

  // ── Action handlers ──
  const entryNode = pipeline
    ? pipeline.nodes.find((n) => n.id === pipeline.entryNodeId) ?? pipeline.nodes[0]
    : undefined;

  const handleExecute = React.useCallback(
    async (runInputs: Record<string, string> = {}) => {
      setActionLoading("execute");
      try {
        const started = await api.post<{ status?: string; error?: string }>(
          `/api/pipelines/${pipelineId}/execute`,
          { inputs: runInputs }
        );
        setRunInputsOpen(false);
        // O run pode nascer "failed" (clone falhou, branch inexistente...):
        // mostra o motivo em vez de "Pipeline iniciada".
        if (started?.status === "failed") {
          addToast("error", started.error ? `Falha ao iniciar: ${started.error}` : "Falha ao iniciar a pipeline.");
        } else {
          addToast("success", "Pipeline iniciada.");
        }
        // Novo run: estados e saídas do anterior deixam de valer.
        setNodeStatuses((prev) => {
          const next = { ...prev };
          for (const key of Object.keys(next)) next[key] = "pending";
          return next;
        });
        setAgentOutputs({});
        setLogs([]);
        setStatusEvents([]);
        setChangedFilesCount(0);
        changeTab("resultado");
        const runsRes = await api.list<PipelineRun>(`/api/pipelines/${pipelineId}/runs`, { page: 1, limit: 50 });
        setRuns(runsRes.items);
        setActiveRun(latestRun(runsRes.items));
      } catch (err) {
        if (err instanceof ApiError) {
          if (err.status === 409) addToast("warning", "Pipeline já está em execução.");
          else addToast("error", err.message);
        } else {
          addToast("error", "Falha ao iniciar a pipeline.");
        }
      } finally {
        setActionLoading(null);
      }
    },
    [pipelineId, addToast, changeTab]
  );

  const runAction = React.useCallback(
    async (
      action: "pause" | "resume" | "stop",
      message: string,
      status: PipelineRun["status"],
      fallbackError: string
    ) => {
      setActionLoading(action);
      try {
        await api.post(`/api/pipelines/${pipelineId}/${action}`, {});
        addToast("info", message);
        setActiveRun((prev) => (prev ? { ...prev, status } : prev));
      } catch (err) {
        addToast("error", err instanceof ApiError ? err.message : fallbackError);
      } finally {
        setActionLoading(null);
      }
    },
    [pipelineId, addToast]
  );

  const handleResumeFromCheckpoint = React.useCallback(
    async (checkpointId: string) => {
      setActionLoading(`resume-cp-${checkpointId}`);
      try {
        await api.post(`/api/pipelines/${pipelineId}/checkpoints/${checkpointId}/resume`, {});
        addToast("info", "Pipeline retomada do checkpoint.");
        setActiveRun((prev) => (prev ? { ...prev, status: "running" } : prev));
      } catch (err) {
        addToast("error", err instanceof ApiError ? err.message : "Falha ao retomar do checkpoint.");
      } finally {
        setActionLoading(null);
      }
    },
    [pipelineId, addToast]
  );

  const handlePublish = React.useCallback(async () => {
    if (!activeRun) return;
    setPublishing(true);
    try {
      const updated = await api.post<PipelineRun>(`/api/runs/${activeRun.id}/publish`, {});
      setActiveRun(updated);
      setRuns((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
      if (updated.publishStatus === "published") addToast("success", "Pull Request publicado.");
      else if (updated.publishStatus === "failed") addToast("error", "A publicação falhou de novo.");
    } catch (err) {
      addToast("error", err instanceof ApiError ? err.message : "Falha ao publicar o PR.");
    } finally {
      setPublishing(false);
    }
  }, [activeRun, addToast]);

  // ── Loading / not found / error ──
  if (loading) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <Skeleton height={32} width={240} />
        <Skeleton height={32} />
        <Skeleton height={36} />
        <Skeleton height={320} />
      </div>
    );
  }

  if (notFound) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="Pipeline não encontrada"
        description="Esta pipeline não existe ou foi excluída."
      />
    );
  }

  if (error) {
    return (
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
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>Falha ao carregar o monitor</div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{error}</div>
        </div>
        <Button size="sm" onClick={() => void fetchAll()} aria-label="Tentar novamente">
          <RefreshCw size={12} aria-hidden="true" />
          Tentar novamente
        </Button>
      </div>
    );
  }

  if (!pipeline) return null;

  const isRunning = activeRun?.status === "running";
  const isPaused = activeRun?.status === "paused";

  const actions = (
    <>
      {!isRunning && !isPaused && (
        <Button
          size="sm"
          variant="primary"
          onClick={() => {
            if (entryNode && (entryNode.agentSnapshot.inputs?.length ?? 0) > 0) setRunInputsOpen(true);
            else void handleExecute();
          }}
          loading={actionLoading === "execute"}
          aria-label="Iniciar execução"
        >
          <Play size={13} aria-hidden="true" />
          Iniciar
        </Button>
      )}
      {isRunning && (
        <Button
          size="sm"
          onClick={() => void runAction("pause", "Pipeline pausada.", "paused", "Falha ao pausar a pipeline.")}
          loading={actionLoading === "pause"}
          aria-label="Pausar"
        >
          <Pause size={13} aria-hidden="true" />
          Pausar
        </Button>
      )}
      {isPaused && (
        <Button
          size="sm"
          variant="primary"
          onClick={() => void runAction("resume", "Pipeline retomada.", "running", "Falha ao retomar a pipeline.")}
          loading={actionLoading === "resume"}
          aria-label="Retomar"
        >
          <Play size={13} aria-hidden="true" />
          Retomar
        </Button>
      )}
      {(isRunning || isPaused) && (
        <Button
          size="sm"
          onClick={() => void runAction("stop", "Pipeline parada.", "cancelled", "Falha ao parar a pipeline.")}
          loading={actionLoading === "stop"}
          style={{ color: "var(--error)" }}
          aria-label="Parar"
        >
          <Square size={13} aria-hidden="true" />
          Parar
        </Button>
      )}
      <Button size="sm" onClick={() => setGraphOpen(true)}>
        <Network size={13} aria-hidden="true" />
        Ver grafo
      </Button>
      <Button size="sm" onClick={() => void fetchAll()} aria-label="Atualizar">
        <RefreshCw size={13} aria-hidden="true" />
      </Button>
    </>
  );

  const tabs: TabItem[] = [
    { id: "resultado", label: "Resultado" },
    ...(activeRun ? [{ id: "arquivos", label: `Arquivos (${changedFilesCount} alterados)` }] : []),
    { id: "logs", label: `Logs (${logs.length})`, error: hasErrorLogs },
    { id: "historico", label: `Histórico (${runs.length})` },
  ];
  // "Arquivos" só existe com um run; na URL sem run, cai no Resultado.
  const shownTab: MonitorTab = activeTab === "arquivos" && !activeRun ? "resultado" : activeTab;

  return (
    <div>
      <RunHeader
        pipeline={pipeline}
        run={activeRun}
        onPublish={() => void handlePublish()}
        actions={actions}
        publishing={publishing}
      />

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

      <div style={{ marginBottom: 12 }}>
        <StageStrip steps={stages} onSelect={focusResult} />
      </div>

      <Tabs
        tabs={tabs}
        activeTab={shownTab}
        onTabChange={(id) => changeTab(id as MonitorTab)}
        idPrefix="monitor"
      />

      <div role="tabpanel" id="monitor-panel" aria-labelledby={`monitor-tab-${shownTab}`} style={{ paddingTop: 16 }}>
        {shownTab === "resultado" && (
          <ResultsTab steps={resultSteps} timeline={timeline} focusNodeId={focus?.nodeId} focusKey={focus?.key} />
        )}
        {shownTab === "arquivos" && activeRun && (
          <FilesTab runId={activeRun.id} refreshKey={filesVersion} onChangedCount={setChangedFilesCount} />
        )}
        {shownTab === "logs" && <LogsTab logs={logs} agents={agents} />}
        {shownTab === "historico" && (
          <HistoryTab
            runs={runs}
            checkpoints={checkpoints}
            onResumeCheckpoint={(id) => void handleResumeFromCheckpoint(id)}
            actionLoading={actionLoading}
          />
        )}
      </div>

      <Modal open={graphOpen} onClose={() => setGraphOpen(false)} title="Grafo da pipeline" size="xl">
        <RunGraph
          pipeline={pipeline}
          statuses={nodeStatuses}
          onNodeSelect={(nodeId) => {
            setGraphOpen(false);
            focusResult(nodeId);
          }}
        />
      </Modal>
    </div>
  );
}

/**
 * PipelineMonitor: monitor de execução em tempo real.
 *
 * - Cabeçalho (RunHeader): status do run, repositório, link do PR / falha de
 *   publicação com nova tentativa, ações (iniciar, pausar, retomar, parar).
 * - Faixa de etapas (StageStrip) na ordem do grafo; clique foca o resultado.
 * - Abas (?tab=): Resultado (markdown, largura total), Arquivos do projeto
 *   (só com run), Logs (filtros por agente e nível) e Histórico.
 * - "Ver grafo": grafo somente leitura num modal grande.
 * - Reconexão do WebSocket: refaz o estado via REST.
 *
 * Endpoints: GET /api/pipelines/{id}, /runs, /checkpoints; POST execute,
 * pause, resume, stop, checkpoints/{cpId}/resume; POST /api/runs/{id}/publish;
 * GET /api/runs/{id}/files, /files/content, /diff, /archive.
 *
 * WS (filtrado por pipelineId): pipeline:status, pipeline:log, agent:output,
 * approval:new, approval:resolved.
 */
export function PipelineMonitor(props: PipelineMonitorProps) {
  return (
    <ReactFlowProvider>
      <PipelineMonitorInner {...props} />
    </ReactFlowProvider>
  );
}
