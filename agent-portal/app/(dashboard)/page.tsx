"use client";

import * as React from "react";
import Link from "next/link";
import { Plus, Bot, RefreshCw, GitBranch, CheckCircle2, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { SkeletonRows } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import {
  AgentCard,
  StatsStrip,
  RecentRuns,
  PendingApprovals,
  OnboardingChecklist,
  type RecentRunItem,
} from "@/components/dashboard";
import { api } from "@/lib/api";
import { plural } from "@/lib/plural";
import { getWebSocketClient, disposeWebSocketClient } from "@/lib/websocket";
import { filterAgentsBySearchAndType } from "@/lib/agent-filter";
import type {
  Agent,
  ApprovalRequest,
  Pipeline,
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
  totalAgents: number;
  totalPipelines: number;
  knowledgeCount: number;
  mcpCount: number;
  runningPipelines: { id: string; name: string }[];
  recentRuns: RecentRunItem[];
  pendingApprovals: ApprovalRequest[];
}

/** Contagem leve (total) de uma listagem; falha não bloqueia o dashboard. */
async function countList(path: string): Promise<number> {
  try {
    const res = await api.list<unknown>(path, { page: 1, limit: 1 });
    return res?.total ?? 0;
  } catch {
    return 0;
  }
}

async function fetchDashboardData(
  typeFilter: string | null
): Promise<DashboardData> {
  const [agentsRes, approvalsRes] = await Promise.all([
    api.list<Agent>("/api/agents", {
      page: 1,
      limit: 50,
      query: { type: typeFilter ?? undefined },
    }),
    api.list<ApprovalRequest>("/api/approvals", {
      page: 1,
      limit: 20,
      query: { status: "pending" },
    }),
  ]);

  const agents = agentsRes.items;
  const pendingApprovals = approvalsRes.items;

  // Runs recentes: para cada pipeline do usuário, busca os runs e filtra por
  // 24h. (Antes do CRUD de pipelines existir, só as pipelines com aprovação
  // pendente eram consideradas e runs concluídos nunca apareciam.)
  const pipelineNames = new Map<string, string>();
  let totalPipelines = 0;
  try {
    const pipelinesRes = await api.list<Pipeline>("/api/pipelines", { page: 1, limit: 50 });
    totalPipelines = pipelinesRes.total;
    for (const p of pipelinesRes.items) pipelineNames.set(p.id, p.name);
  } catch {
    // Listagem indisponível: cai nas pipelines das aprovações pendentes.
  }

  // Contagens para o checklist de onboarding (falha não bloqueia).
  const [knowledgeCount, mcpCount] = await Promise.all([
    countList("/api/knowledge"),
    countList("/api/mcp-servers"),
  ]);
  const pipelineIds = new Set<string>(pipelineNames.keys());
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
          recentRuns.push({ run, pipelineName: pipelineNames.get(pipelineId) });
        }
        if (run.status === "running") {
          runningPipelines.push({ id: pipelineId, name: pipelineNames.get(pipelineId) ?? pipelineId });
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

  return {
    agents,
    totalAgents: agentsRes.total,
    totalPipelines,
    knowledgeCount,
    mcpCount,
    runningPipelines,
    recentRuns,
    pendingApprovals,
  };
}

export default function DashboardPage() {
  const { addToast } = useToast();
  const [data, setData] = React.useState<DashboardData | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [search, setSearch] = React.useState("");
  const [typeFilter, setTypeFilter] = React.useState("");

  const load = React.useCallback(
    async (typeOverride?: string) => {
      setLoading(true);
      setError(null);
      const type = typeOverride !== undefined ? typeOverride : typeFilter;
      try {
        const result = await fetchDashboardData(type || null);
        setData(result);
      } catch (e) {
        const message =
          e instanceof Error ? e.message : "Falha ao carregar o dashboard";
        setError(message);
        addToast("error", message);
      } finally {
        setLoading(false);
      }
    },
    [typeFilter, addToast]
  );

  React.useEffect(() => {
    void load();
  }, [load]);

  const handleTypeChange = React.useCallback(
    (value: string) => {
      setTypeFilter(value);
      void load(value);
    },
    [load]
  );

  const agentTypes = React.useMemo(() => {
    if (!data) return [];
    const seen = new Map<string, number>();
    for (const agent of data.agents) {
      seen.set(agent.type, (seen.get(agent.type) ?? 0) + 1);
    }
    return Array.from(seen.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([value, count]) => ({ value, label: `${value} (${count})` }));
  }, [data]);

  const visibleAgents = React.useMemo(
    () => (data ? filterAgentsBySearchAndType(data.agents, search, typeFilter) : []),
    [data, search, typeFilter]
  );

  const noMatch =
    data !== null && data.agents.length > 0 && visibleAgents.length === 0;

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

  // Portal vazio: sem agentes e sem pipelines → onboarding, sem métricas.
  const isEmpty =
    data !== null && data.agents.length === 0 && data.totalPipelines === 0;

  // Checklist de onboarding: aparece enquanto faltar algum item básico.
  const showChecklist =
    data !== null &&
    !(
      data.agents.length > 0 &&
      data.totalPipelines > 0 &&
      data.knowledgeCount > 0 &&
      data.mcpCount > 0
    );

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
            Overview
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
              : `${plural(data?.totalAgents ?? 0, "agente", "agentes")} · ${plural(stats.runningPipelines, "pipeline", "pipelines")} em execução`}
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

      {/* Stats strip (oculto enquanto o portal está vazio) */}
      {!isEmpty && (
        <div style={{ marginBottom: "20px" }}>
          <StatsStrip stats={stats} loading={loading} />
        </div>
      )}

      {/* Checklist de onboarding (enquanto faltarem itens básicos) */}
      {data && !loading && !error && showChecklist && (
        <OnboardingChecklist
          hasAgent={data.agents.length > 0}
          hasPipeline={data.totalPipelines > 0}
          hasKnowledge={data.knowledgeCount > 0}
          hasMcp={data.mcpCount > 0}
        />
      )}

      {/* Grid de agentes / estado de primeiro uso (portal vazio) */}
      {!isEmpty && (
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
          <div
            role="search"
            aria-label="Buscar e filtrar agentes"
            style={{
              display: "flex",
              gap: "8px",
              flexWrap: "wrap",
              marginBottom: "12px",
            }}
          >
            <label
              htmlFor="agents-search"
              style={{ position: "absolute", left: -9999 }}
            >
              Buscar por nome, descrição ou tipo
            </label>
            <input
              id="agents-search"
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar por nome, descrição ou tipo…"
              style={{
                flex: "1 1 220px",
                minWidth: 180,
                padding: "10px 14px",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border)",
                background: "var(--bg-elevated)",
                color: "var(--text)",
                fontSize: "13px",
                fontFamily: "var(--font)",
                outline: "none",
                transition: "border-color var(--transition)",
              }}
            />
            <label
              htmlFor="agents-type-filter"
              style={{ position: "absolute", left: -9999 }}
            >
              Filtrar por tipo
            </label>
            <select
              id="agents-type-filter"
              value={typeFilter}
              onChange={(e) => handleTypeChange(e.target.value)}
              style={{
                flex: "1 1 180px",
                minWidth: 150,
                padding: "10px 14px",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border)",
                background: "var(--bg-elevated)",
                color: "var(--text)",
                fontSize: "13px",
                fontFamily: "var(--font)",
                outline: "none",
                cursor: "pointer",
                transition: "border-color var(--transition)",
              }}
            >
              <option value="">Todos os tipos</option>
              {agentTypes.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.value}
                </option>
              ))}
            </select>
          </div>
        {loading ? (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
              gap: "12px",
            }}
          >
            {[0, 1, 2, 3].map((i) => (
              <Card key={i} style={{ minHeight: 128 }}>
                <SkeletonRows rows={3} height={14} gap={8} />
              </Card>
            ))}
          </div>
        ) : noMatch && !loading && !error ? (
          <EmptyState
            icon={Search}
            title="Nenhum agente encontrado"
            description="Nenhum agente corresponde à busca e ao filtro. Limpe os filtros para ver todos os agentes."
            action={
              <Button
                onClick={() => {
                  setSearch("");
                  handleTypeChange("");
                }}
              >
                Limpar filtros
              </Button>
            }
          />
        ) : data && data.agents.length > 0 ? (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
              gap: "12px",
            }}
          >
            {visibleAgents.map((agent) => (
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
      )}

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
