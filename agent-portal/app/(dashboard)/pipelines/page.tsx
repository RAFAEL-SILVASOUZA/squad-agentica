"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { GitBranch, Plus, RefreshCw, AlertTriangle, Monitor } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Pipeline, PipelineRun, PaginatedResponse } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { useToast } from "@/components/ui/toast";
import { PipelineActionsMenu } from "@/components/pipelines/pipeline-actions-menu";

const PAGE_SIZE = 20;

/**
 * Pipelines list page.
 * Shows all pipelines with status, node/edge counts, and a CTA to create.
 * Portal starts empty (contract §0): empty state with "Criar primeiro pipeline" CTA.
 */

// E11: status da pipeline em pt-BR (o valor do contrato fica em inglês).
const PIPELINE_STATUS_LABEL: Record<string, string> = {
  draft: "Rascunho",
  running: "Executando",
  paused: "Pausado",
  completed: "Concluído",
  failed: "Falhou",
  cancelled: "Cancelado",
};

const RUN_STATUS_LABEL: Record<PipelineRun["status"], string> = {
  running: "Executando",
  paused: "Pausado",
  completed: "Concluído",
  failed: "Falhou",
  cancelled: "Cancelado",
};

function timeSince(iso: string | null | undefined): string {
  if (!iso) return "agora";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "agora";
  const diffMs = Date.now() - date.getTime();
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "agora";
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `há ${hours} h`;
  const days = Math.floor(hours / 24);
  return `há ${days} d`;
}

export default function PipelinesPage() {
  const router = useRouter();
  const { addToast } = useToast();

  const [pipelines, setPipelines] = React.useState<Pipeline[]>([]);
  const [total, setTotal] = React.useState(0);
  const [page, setPage] = React.useState(1);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [creating, setCreating] = React.useState(false);
  const [lastRuns, setLastRuns] = React.useState<Record<string, PipelineRun | null>>({});

  const fetchPipelines = React.useCallback(async (pageNum: number) => {
    setLoading(true);
    setError(null);
    try {
      const res: PaginatedResponse<Pipeline> = await api.list<Pipeline>(
        "/api/pipelines",
        { page: pageNum, limit: PAGE_SIZE }
      );
      setPipelines(res.items);
      setTotal(res.total);
      setPage(pageNum);
    } catch (err) {
      if (err instanceof ApiError) {
        // E12: um 404 (endpoint ausente/corrido) NÃO é "lista vazia":
        // mostra estado de erro com a mensagem real, não o empty state.
        setError(err.status === 404 ? "Endpoint de pipelines indisponível (404). Verifique o backend." : err.message);
      } else {
        setError("Falha ao carregar pipelines");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    fetchPipelines(1);
  }, [fetchPipelines]);

  // Último run de cada pipeline (card: "Último run: Concluído há 5 min").
  React.useEffect(() => {
    let active = true;
    if (pipelines.length === 0) {
      setLastRuns({});
      return;
    }
    (async () => {
      const entries = await Promise.all(
        pipelines.map(async (p) => {
          try {
            const res = await api.list<PipelineRun>(`/api/pipelines/${p.id}/runs`, { page: 1, limit: 1 });
            return [p.id, res.items[0] ?? null] as const;
          } catch {
            return [p.id, null] as const;
          }
        })
      );
      if (active) setLastRuns(Object.fromEntries(entries));
    })();
    return () => {
      active = false;
    };
  }, [pipelines]);

  const handleCreate = React.useCallback(async () => {
    setCreating(true);
    try {
      const res = await api.post<Pipeline>("/api/pipelines", {
        name: "Novo pipeline",
        description: "",
        entryNodeId: "",
        nodes: [],
        edges: [],
      });
      // ?new=1: o editor já abre com o nome em edição.
      router.push(`/pipelines/${res.id}?new=1`);
    } catch (err) {
      if (err instanceof ApiError) {
        addToast("error", err.message);
      } else {
        addToast("error", "Falha ao criar pipeline");
      }
    } finally {
      setCreating(false);
    }
  }, [router, addToast]);

  const handlePipelineDuplicated = React.useCallback(
    (id: string) => {
      router.push(`/pipelines/${id}`);
    },
    [router]
  );

  const handlePipelineDeleted = React.useCallback(() => {
    addToast("success", "Pipeline excluído.");
    void fetchPipelines(page);
  }, [addToast, fetchPipelines, page]);

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
            onClick={() => fetchPipelines(page)}
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

      {/* Empty state */}
      {!loading && !error && pipelines.length === 0 && (
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

      {/* Pipeline cards */}
      {!loading && !error && pipelines.length > 0 && (
        <>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
              gap: 12,
            }}
          >
            {pipelines.map((pipeline) => {
              const lastRun = lastRuns[pipeline.id];
              return (
                <div
                  key={pipeline.id}
                  onClick={() => router.push(`/pipelines/${pipeline.id}`)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") router.push(`/pipelines/${pipeline.id}`);
                    if (e.key === " ") {
                      e.preventDefault();
                      router.push(`/pipelines/${pipeline.id}`);
                    }
                  }}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                    padding: 16,
                    background: "var(--bg-elevated)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius)",
                    cursor: "pointer",
                    transition: "border-color 0.2s",
                    textAlign: "left",
                    position: "relative",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 8,
                    }}
                  >
                    <span
                      style={{
                        fontSize: 14,
                        fontWeight: 600,
                        color: "var(--text)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        flex: 1,
                      }}
                    >
                      {pipeline.name}
                    </span>
                    <Badge
                      status={
                        pipeline.status === "running"
                          ? "running"
                          : pipeline.status === "failed"
                            ? "failed"
                            : pipeline.status === "paused"
                              ? "paused"
                              : "neutral"
                      }
                      label={PIPELINE_STATUS_LABEL[pipeline.status] ?? pipeline.status}
                    />
                    <PipelineActionsMenu
                      pipelineId={pipeline.id}
                      pipelineName={pipeline.name}
                      label={`Mais ações de ${pipeline.name}`}
                      onDuplicated={handlePipelineDuplicated}
                      onDeleted={handlePipelineDeleted}
                    />
                  </div>

                  {pipeline.description && (
                    <span
                      style={{
                        fontSize: 12,
                        color: "var(--text-secondary)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {pipeline.description}
                    </span>
                  )}

                  {pipeline.repository && (
                    <span
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 6,
                        fontSize: 11,
                        color: "var(--text-secondary)",
                      }}
                    >
                      <GitBranch size={11} aria-hidden="true" />
                      {pipeline.repository.fullName} ({pipeline.repository.baseBranch})
                    </span>
                  )}

                  <div
                    style={{
                      display: "flex",
                      gap: 12,
                      fontSize: 11,
                      color: "var(--text-muted)",
                      marginTop: 4,
                    }}
                  >
                    <span>{pipeline.nodes.length} {pipeline.nodes.length === 1 ? "nó" : "nós"}</span>
                    <span>{pipeline.edges.length} {pipeline.edges.length === 1 ? "aresta" : "arestas"}</span>
                  </div>

                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      marginTop: 4,
                      paddingTop: 8,
                      borderTop: "1px solid var(--border)",
                    }}
                  >
                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                      {lastRun
                        ? `Último run: ${RUN_STATUS_LABEL[lastRun.status] ?? lastRun.status} ${timeSince(lastRun.completedAt ?? lastRun.startedAt)}`
                        : "Sem execuções"}
                    </span>
                    <Link
                      href={`/pipelines/${pipeline.id}/run`}
                      aria-label={`Ver monitor de ${pipeline.name}`}
                      onClick={(e) => e.stopPropagation()}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 4,
                        fontSize: 11,
                        color: "var(--accent)",
                        textDecoration: "none",
                      }}
                    >
                      <Monitor size={11} aria-hidden="true" />
                      Monitor
                    </Link>
                  </div>
                </div>
              );
            })}
          </div>

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
                onClick={() => fetchPipelines(page - 1)}
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
                onClick={() => fetchPipelines(page + 1)}
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
