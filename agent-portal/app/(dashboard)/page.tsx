"use client";

import * as React from "react";
import Link from "next/link";
import { Plus, Bot, RefreshCw, GitBranch, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { useToast } from "@/components/ui/toast";
import {
  AgentCard,
  StatsStrip,
  RecentRuns,
  PendingApprovals,
  type RecentRunItem,
} from "@/components/dashboard";
import { api } from "@/lib/api";
import { getWebSocketClient, disposeWebSocketClient } from "@/lib/websocket";
import type {
  Agent,
  ApprovalRequest,
  PipelineRun,
  PipelineStatusEvent,
} from "@/lib/types";

/**
 * Dashboard (protótipo view-dashboard, fe-dashboard).
 * - Header: título + contagem + botão "Novo Agente" (real → /agents/new).
 * - Stats strip: pipelines em execução, runs 24h, runs concluídos, aprovações pendentes.
 * - Grid de agentes (cards clicáveis → /agents/{id}).
 * - Runs recentes (status em tempo real via WS pipeline:status).
 * - Aprovações pendentes (link → /approvals).
 *
 * Portal nasce vazio (contrato §0): sem seed ilustrativo.
 * Estados: loading (skeleton), vazio (EmptyState com CTA), erro (toast + retry).
 */

const DAY_MS = 24 * 60 * 60 * 1000;

interface DashboardData {
  agents: Agent[];
  runningPipelines: { id: string; name: string }[];
  recentRuns: RecentRunItem[];
  pendingApprovals: ApprovalRequest[];
}

async function fetchDashboardData(): Promise<DashboardData> {
  const [agentsRes, approvalsRes] = await Promise.all([
    api.list<Agent>("/api/agents", { page: 1, limit: 50 }),
    api.list<ApprovalRequest>("/api/approvals", {
      page: 1,
      limit: 20,
      query: { status: "pending" },
    }),
  ]);

  const agents = agentsRes.items;
  const pendingApprovals = approvalsRes.items;

  // Runs recentes: para cada pipeline, busca os runs e filtra por 24h.
  // O backend não expõe listagem global de pipelines (contrato §9), então
  // derivamos pipelines dos agentes e das aprovações pendentes.
  const pipelineIds = new Set<string>();
  for (const approval of pendingApprovals) {
    pipelineIds.add(approval.pipelineId);
  }

  const recentRuns: RecentRunItem[] = [];
  const runningPipelines: { id: string; name: string }[] = [];
  const cutoff = Date.now() - DAY_MS;

  for (const pipelineId of pipelineIds) {
    try {
      const runsRes = await api.list<PipelineRun>(
        `/api/pipelines/${pipelineId}/runs`,
        { page: 1, limit: 20 }
      );
      for (const run of runsRes.items) {
        const started = run.startedAt ? new Date(run.startedAt).getTime() : 0;
        if (started >= cutoff) {
          recentRuns.push({ run, pipelineName: undefined });
        }
        if (run.status === "running") {
          runningPipelines.push({ id: pipelineId, name: pipelineId });
        }
      }
    } catch {
      // Pipeline inexistente ou sem acesso: ignora (não bloqueia o dashboard).
    }
  }

  recentRuns.sort(
    (a, b) =>
      new Date(b.run.startedAt ?? 0).getTime() -
      new Date(a.run.startedAt ?? 0).getTime()
  );

  return { agents, runningPipelines, recentRuns, pendingApprovals };
}

export default function DashboardPage() {
  const { addToast } = useToast();
  const [data, setData] = React.useState<DashboardData | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchDashboardData();
      setData(result);
    } catch (e) {
      const message =
        e instanceof Error ? e.message : "Falha ao carregar o dashboard";
      setError(message);
      addToast("error", message);
    } finally {
      setLoading(false);
    }
  }, [addToast]);

  React.useEffect(() => {
    void load();
  }, [load]);

  // WebSocket: pipeline:status atualiza runs recentes em tempo real.
  // Ao reconectar, refetch via REST (contrato §7).
  // O token vem do mesmo endpoint que lib/api.ts usa (GET /api/session-token);
  // em produção o token é cacheado em memória pelo lib/api.ts.
  React.useEffect(() => {
    let client: ReturnType<typeof getWebSocketClient> | null = null;
    let onStatus: ((eventData: Record<string, unknown>) => void) | null = null;
    let onReconnect: (() => void) | null = null;

    const connect = async () => {
      try {
        const tokenRes = await fetch("/api/session-token", {
          method: "GET",
          credentials: "same-origin",
        });
        if (!tokenRes.ok) return;
        const { accessToken } = (await tokenRes.json()) as {
          accessToken: string;
        };
        client = getWebSocketClient(accessToken);

        onStatus = (eventData: Record<string, unknown>) => {
          const event = eventData as unknown as PipelineStatusEvent;
          if (!event.pipelineId || !event.runId) return;
          const statusMap: Record<
            PipelineStatusEvent["status"],
            PipelineRun["status"]
          > = {
            pending: "paused",
            running: "running",
            completed: "completed",
            failed: "failed",
            waiting_approval: "paused",
          };
          const runStatus = statusMap[event.status];
          setData((prev) => {
            if (!prev) return prev;
            const recentRuns = prev.recentRuns.map((item) =>
              item.run.id === event.runId
                ? { ...item, run: { ...item.run, status: runStatus } }
                : item
            );
            return { ...prev, recentRuns };
          });
        };

        onReconnect = () => {
          void load();
        };

        client.on("pipeline:status", onStatus);
        client.onReconnect(onReconnect);
        client.connect();
      } catch {
        // WS indisponível: o dashboard segue com REST (refetch manual).
      }
    };

    void connect();

    return () => {
      if (client && onStatus) {
        client.off("pipeline:status", onStatus);
      }
      disposeWebSocketClient();
    };
  }, [load]);

  const stats = React.useMemo(() => {
    if (!data) {
      return {
        runningPipelines: 0,
        recentRuns: 0,
        completedRuns: 0,
        pendingApprovals: 0,
      };
    }
    const completedRuns = data.recentRuns.filter(
      (item) => item.run.status === "completed"
    ).length;
    return {
      runningPipelines: data.runningPipelines.length,
      recentRuns: data.recentRuns.length,
      completedRuns,
      pendingApprovals: data.pendingApprovals.length,
    };
  }, [data]);

  const isEmpty = data !== null && data.agents.length === 0;

  return (
    <div>
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: "16px",
          marginBottom: "20px",
          flexWrap: "wrap",
        }}
      >
        <div>
          <h1
            style={{
              fontSize: "20px",
              fontWeight: 700,
              color: "var(--text)",
              margin: 0,
            }}
          >
            Agentes
          </h1>
          <p
            style={{
              fontSize: "12px",
              color: "var(--text-secondary)",
              margin: "4px 0 0",
            }}
          >
            {loading
              ? "Carregando…"
              : `${data?.agents.length ?? 0} agentes · ${stats.runningPipelines} pipelines em execução`}
          </p>
        </div>
        <Link href="/agents/new">
          <Button variant="primary">
            <Plus size={14} aria-hidden="true" />
            Novo Agente
          </Button>
        </Link>
      </div>

      {/* Erro com retry */}
      {error && !loading && (
        <Card style={{ marginBottom: "16px" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "12px",
              flexWrap: "wrap",
            }}
          >
            <span style={{ fontSize: "13px", color: "var(--error)" }}>
              {error}
            </span>
            <Button size="sm" onClick={() => void load()}>
              <RefreshCw size={13} aria-hidden="true" />
              Tentar novamente
            </Button>
          </div>
        </Card>
      )}

      {/* Stats strip */}
      <div style={{ marginBottom: "20px" }}>
        <StatsStrip
          stats={stats}
          runningPipelineId={data?.runningPipelines[0]?.id}
          recentRunPipelineId={data?.recentRuns[0]?.run.pipelineId}
          loading={loading}
        />
      </div>

      {/* Grid de agentes / estado de primeiro uso (portal vazio) */}
      <section aria-labelledby="agents-heading" style={{ marginBottom: "24px" }}>
        <h2
          id="agents-heading"
          style={{
            fontSize: "13px",
            fontWeight: 600,
            color: "var(--text-secondary)",
            textTransform: "uppercase",
            letterSpacing: "0.5px",
            margin: "0 0 10px",
          }}
        >
          Agentes
        </h2>
        {isEmpty && !loading && !error ? (
          <Card style={{ marginBottom: "12px" }}>
            <EmptyState
              icon={Bot}
              title="Comece criando seu primeiro agente"
              description="Crie um agente e depois monte uma pipeline conectando agentes no editor de fluxo. O portal nasce vazio: nada aqui é ilustrativo."
              action={
                <Link href="/agents/new">
                  <Button variant="primary">
                    <Plus size={14} aria-hidden="true" />
                    Criar primeiro agente
                  </Button>
                </Link>
              }
            />
          </Card>
        ) : loading ? (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
              gap: "12px",
            }}
          >
            {[0, 1, 2, 3].map((i) => (
              <Card key={i} style={{ minHeight: 128 }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "10px",
                    marginBottom: "12px",
                  }}
                >
                  <div
                    style={{
                      width: 32,
                      height: 32,
                      borderRadius: "var(--radius-sm)",
                      background: "var(--bg-hover)",
                    }}
                  />
                  <div style={{ flex: 1 }}>
                    <div
                      style={{
                        height: 12,
                        borderRadius: 4,
                        background: "var(--bg-hover)",
                        marginBottom: 6,
                      }}
                    />
                    <div
                      style={{
                        height: 10,
                        width: "60%",
                        borderRadius: 4,
                        background: "var(--bg-hover)",
                      }}
                    />
                  </div>
                </div>
                <div
                  style={{
                    height: 14,
                    width: "40%",
                    borderRadius: 4,
                    background: "var(--bg-hover)",
                  }}
                />
              </Card>
            ))}
          </div>
        ) : data && data.agents.length > 0 ? (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
              gap: "12px",
            }}
          >
            {data.agents.map((agent) => (
              <AgentCard
                key={agent.id}
                agent={agent}
                status="idle"
              />
            ))}
          </div>
        ) : (
          !error && (
            <EmptyState
              icon={Bot}
              title="Nenhum agente ainda"
              description="Crie seu primeiro agente para começar a montar pipelines."
              action={
                <Link href="/agents/new">
                  <Button variant="primary">
                    <Plus size={14} aria-hidden="true" />
                    Criar primeiro agente
                  </Button>
                </Link>
              }
            />
          )
        )}
      </section>

      {/* Runs recentes + aprovações pendentes */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
          gap: "20px",
        }}
      >
        <section aria-labelledby="runs-heading">
          <h2
            id="runs-heading"
            style={{
              fontSize: "13px",
              fontWeight: 600,
              color: "var(--text-secondary)",
              textTransform: "uppercase",
              letterSpacing: "0.5px",
              margin: "0 0 10px",
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            <GitBranch size={13} aria-hidden="true" />
            Runs recentes
          </h2>
          <RecentRuns
            items={data?.recentRuns ?? []}
            loading={loading}
          />
        </section>

        <section aria-labelledby="approvals-heading">
          <h2
            id="approvals-heading"
            style={{
              fontSize: "13px",
              fontWeight: 600,
              color: "var(--text-secondary)",
              textTransform: "uppercase",
              letterSpacing: "0.5px",
              margin: "0 0 10px",
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            <CheckCircle2 size={13} aria-hidden="true" />
            Aprovações pendentes
          </h2>
          <PendingApprovals
            items={data?.pendingApprovals ?? []}
            loading={loading}
          />
        </section>
      </div>
    </div>
  );
}
