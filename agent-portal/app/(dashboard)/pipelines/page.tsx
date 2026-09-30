"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { GitBranch, Plus, RefreshCw, AlertTriangle, Monitor } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Pipeline, PaginatedResponse } from "@/lib/types";
import { useCreatePipelineAndNavigate } from "@/lib/create-pipeline";
import { relativeTime } from "@/lib/relative-time";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { DataTable } from "@/components/ui/data-table";
import { useToast } from "@/components/ui/toast";
import { PipelineActionsMenu } from "@/components/pipelines/pipeline-actions-menu";

const PAGE_SIZE = 20;

const RUN_STATUS_LABEL: Record<string, string> = {
  running: "Executando",
  paused: "Pausado",
  completed: "Concluído",
  failed: "Falhou",
  cancelled: "Cancelado",
};

const RUN_FILTER_OPTIONS = [
  { value: "running", label: "Executando" },
  { value: "completed", label: "Concluído" },
  { value: "failed", label: "Falhou" },
  { value: "never", label: "Sem execuções" },
];

/** Pipeline com campo flat para o filtro client-side do DataTable. */
interface PipelineRow extends Pipeline {
  lastRunStatus: string;
}

export default function PipelinesPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { addToast } = useToast();

  const [pipelines, setPipelines] = React.useState<Pipeline[]>([]);
  const [total, setTotal] = React.useState(0);
  const [page, setPage] = React.useState(1);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [creating, setCreating] = React.useState(false);

  // Filtro `run` vem da URL (?run=running) para deep-linking.
  const runFilter = searchParams.get("run") ?? "";

  const fetchPipelines = React.useCallback(
    async (pageNum: number, run?: string) => {
      setLoading(true);
      setError(null);
      try {
        const params: Record<string, string | number> = { page: pageNum, limit: PAGE_SIZE };
        if (run) params.run = run;
        const res: PaginatedResponse<Pipeline> = await api.list<Pipeline>(
          "/api/pipelines",
          params
        );
        setPipelines(res.items);
        setTotal(res.total);
        setPage(pageNum);
      } catch (err) {
        if (err instanceof ApiError) {
          setError(
            err.status === 404
              ? "Endpoint de pipelines indisponível (404). Verifique o backend."
              : err.message
          );
        } else {
          setError("Falha ao carregar pipelines");
        }
      } finally {
        setLoading(false);
      }
    },
    []
  );

  React.useEffect(() => {
    fetchPipelines(1, runFilter || undefined);
  }, [fetchPipelines, runFilter]);

  const createPipelineAndNavigate = useCreatePipelineAndNavigate();

  const handleCreate = React.useCallback(async () => {
    setCreating(true);
    try {
      await createPipelineAndNavigate();
    } finally {
      setCreating(false);
    }
  }, [createPipelineAndNavigate]);

  const handlePipelineDuplicated = React.useCallback(
    (id: string) => {
      router.push(`/pipelines/${id}`);
    },
    [router]
  );

  const handlePipelineDeleted = React.useCallback(() => {
    addToast("success", "Pipeline excluído.");
    void fetchPipelines(page, runFilter || undefined);
  }, [addToast, fetchPipelines, page, runFilter]);

  const handleRowMenu = React.useCallback(
    (pipeline: Pipeline, action: string) => {
      if (action === "open") {
        router.push(`/pipelines/${pipeline.id}`);
      } else if (action === "monitor") {
        router.push(`/pipelines/${pipeline.id}/run`);
      }
    },
    [router]
  );

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div>
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 24,
        }}
      >
        <div>
          <h1
            style={{
              fontSize: "var(--text-title)",
              fontWeight: 700,
              color: "var(--text)",
              margin: 0,
            }}
          >
            Pipelines
          </h1>
          <p
            style={{
              fontSize: "var(--text-lg)",
              color: "var(--text-secondary)",
              margin: "4px 0 0",
            }}
          >
            Gerencie os pipelines de agentes
          </p>
        </div>
        <Button
          variant="primary"
          onClick={handleCreate}
          disabled={creating}
          aria-label="Criar novo pipeline"
        >
          <Plus size={14} aria-hidden="true" />
          {creating ? "Criando..." : "Novo pipeline"}
        </Button>
      </div>

      {/* Error state */}
      {error && !loading && (
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
              Falha ao carregar pipelines
            </div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{error}</div>
          </div>
          <Button
            size="sm"
            onClick={() => fetchPipelines(page, runFilter || undefined)}
            aria-label="Carregar pipelines de novo"
          >
            <RefreshCw size={12} aria-hidden="true" />
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
            gap: 12,
          }}
        >
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} height={100} />
          ))}
        </div>
      )}

      {/* Empty state: só quando não há pipelines E nenhum filtro ativo */}
      {!loading && !error && pipelines.length === 0 && !runFilter && (
        <EmptyState
          icon={GitBranch}
          title="Nenhum pipeline ainda"
          description="Crie o primeiro pipeline para orquestrar agentes."
          action={
            <Button
              variant="primary"
              onClick={handleCreate}
              disabled={creating}
              aria-label="Criar primeiro pipeline"
            >
              <Plus size={14} aria-hidden="true" />
              Criar primeiro pipeline
            </Button>
          }
        />
      )}

      {/* DataTable: mostra sempre que há pipelines OU filtro ativo (para o usuário limpar o filtro) */}
      {!loading && !error && (pipelines.length > 0 || runFilter) && (
        <>
          <DataTable<PipelineRow>
            columns={[
              {
                key: "name",
                header: "Nome",
                sortable: true,
                render: (p) => (
                  <Link
                    href={`/pipelines/${p.id}`}
                    style={{ color: "var(--text)", fontWeight: 600, textDecoration: "none" }}
                  >
                    {p.name}
                  </Link>
                ),
              },
              {
                key: "repository",
                header: "Repositório",
                render: (p) =>
                  p.repository ? (
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                      <GitBranch size={11} aria-hidden="true" />
                      {p.repository.fullName}
                    </span>
                  ) : (
                    <span style={{ color: "var(--text-muted)" }}>—</span>
                  ),
              },
              {
                key: "runStats",
                header: "Últimos 10 runs",
                render: (p) => {
                  if (!p.runStats) return <span style={{ color: "var(--text-muted)" }}>—</span>;
                  return (
                    <span style={{ fontSize: 12 }}>
                      <span style={{ color: "var(--success, #22c55e)" }}>✓ {p.runStats.recentSucceeded}</span>
                      {" · "}
                      <span style={{ color: "var(--error, #ef4444)" }}>✗ {p.runStats.recentFailed}</span>
                    </span>
                  );
                },
              },
              {
                key: "lastRun",
                header: "Último run",
                render: (p) => {
                  if (!p.runStats?.lastRunStatus) {
                    return <span style={{ color: "var(--text-muted)" }}>Sem execuções</span>;
                  }
                  const label = RUN_STATUS_LABEL[p.runStats.lastRunStatus] ?? p.runStats.lastRunStatus;
                  const time = p.runStats.lastRunAt ? relativeTime(p.runStats.lastRunAt) : "";
                  return (
                    <span style={{ fontSize: 12 }}>
                      {label} {time}
                    </span>
                  );
                },
              },
              {
                key: "updatedAt",
                header: "Atualizado",
                sortable: true,
                render: (p) =>
                  p.updatedAt ? (
                    <span style={{ color: "var(--text-secondary)" }}>{relativeTime(p.updatedAt)}</span>
                  ) : (
                    <span style={{ color: "var(--text-muted)" }}>—</span>
                  ),
              },
            ]}
            rows={pipelines.map((p) => ({
              ...p,
              lastRunStatus: p.runStats?.lastRunStatus ?? "never",
            }))}
            rowKey={(p) => p.id}
            searchPlaceholder="Buscar pipelines…"
            filters={[
              {
                key: "lastRunStatus",
                label: "Último run",
                options: RUN_FILTER_OPTIONS,
              },
            ]}
            initialFilterValues={runFilter ? { lastRunStatus: runFilter } : undefined}
            onFilterChange={(values) => {
              const run = values.lastRunStatus || "";
              const params = new URLSearchParams();
              if (run) params.set("run", run);
              router.replace(`/pipelines${params.toString() ? `?${params}` : ""}`);
            }}
            onRowMenu={handleRowMenu}
            rowMenuItems={[
              { label: "Abrir", action: "open" },
              { label: "Monitor", action: "monitor" },
            ]}
            rowActions={(p) => (
              <PipelineActionsMenu
                pipelineId={p.id}
                pipelineName={p.name}
                onDuplicated={handlePipelineDuplicated}
                onDeleted={handlePipelineDeleted}
              />
            )}
            emptyMessage="Nenhuma pipeline encontrada"
          />

          {/* Pagination */}
          {totalPages > 1 && (
            <div
              style={{
                display: "flex",
                justifyContent: "center",
                gap: 8,
                marginTop: 20,
              }}
            >
              <Button
                size="sm"
                onClick={() => fetchPipelines(page - 1, runFilter || undefined)}
                disabled={page <= 1}
                aria-label="Página anterior"
              >
                Anterior
              </Button>
              <span
                style={{
                  fontSize: 12,
                  color: "var(--text-secondary)",
                  display: "flex",
                  alignItems: "center",
                  padding: "0 8px",
                }}
              >
                Page {page} of {totalPages}
              </span>
              <Button
                size="sm"
                onClick={() => fetchPipelines(page + 1, runFilter || undefined)}
                disabled={page >= totalPages}
                aria-label="Próxima página"
              >
                Próxima
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
