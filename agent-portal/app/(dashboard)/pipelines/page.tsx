"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { GitBranch, Plus, RefreshCw, AlertTriangle, MoreVertical, Monitor } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Pipeline, PipelineRun, PaginatedResponse } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { Modal } from "@/components/ui/modal";
import { useToast } from "@/components/ui/toast";

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
  const [openMenuId, setOpenMenuId] = React.useState<string | null>(null);
  const [deletingPipeline, setDeletingPipeline] = React.useState<Pipeline | null>(null);
  const [deleteBusy, setDeleteBusy] = React.useState(false);
  const [duplicatingId, setDuplicatingId] = React.useState<string | null>(null);

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

  // Esc/clique fora fecham o menu "Mais ações" do card aberto.
  React.useEffect(() => {
    if (!openMenuId) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpenMenuId(null);
    }
    function onClickOutside(e: MouseEvent) {
      const el = document.getElementById(`pipeline-menu-${openMenuId}`);
      if (el && !el.contains(e.target as Node)) setOpenMenuId(null);
    }
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onClickOutside);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onClickOutside);
    };
  }, [openMenuId]);

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

  const handleDuplicate = React.useCallback(
    async (pipeline: Pipeline) => {
      setOpenMenuId(null);
      setDuplicatingId(pipeline.id);
      try {
        const res = await api.post<Pipeline>(`/api/pipelines/${pipeline.id}/duplicate`);
        addToast("success", "Pipeline duplicado.");
        router.push(`/pipelines/${res.id}`);
      } catch (err) {
        addToast("error", err instanceof ApiError ? err.message : "Não foi possível duplicar o pipeline.");
      } finally {
        setDuplicatingId(null);
      }
    },
    [router, addToast]
  );

  const handleDelete = React.useCallback(async () => {
    if (!deletingPipeline) return;
    setDeleteBusy(true);
    try {
      await api.delete(`/api/pipelines/${deletingPipeline.id}`);
      addToast("success", "Pipeline excluído.");
      setDeletingPipeline(null);
      await fetchPipelines(page);
    } catch (err) {
      addToast("error", err instanceof ApiError ? err.message : "Não foi possível excluir o pipeline.");
    } finally {
      setDeleteBusy(false);
    }
  }, [deletingPipeline, page, fetchPipelines, addToast]);

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
                    <div id={`pipeline-menu-${pipeline.id}`} style={{ position: "relative" }}>
                      <button
                        type="button"
                        aria-haspopup="menu"
                        aria-expanded={openMenuId === pipeline.id}
                        aria-label={`Mais ações de ${pipeline.name}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          setOpenMenuId((prev) => (prev === pipeline.id ? null : pipeline.id));
                        }}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          justifyContent: "center",
                          width: 24,
                          height: 24,
                          background: "none",
                          border: "none",
                          borderRadius: "var(--radius-sm)",
                          color: "var(--text-muted)",
                          cursor: "pointer",
                          flexShrink: 0,
                        }}
                      >
                        <MoreVertical size={14} aria-hidden="true" />
                      </button>
                      {openMenuId === pipeline.id && (
                        <div
                          role="menu"
                          aria-label={`Mais ações de ${pipeline.name}`}
                          onClick={(e) => e.stopPropagation()}
                          style={{
                            position: "absolute",
                            top: "calc(100% + 4px)",
                            right: 0,
                            zIndex: 20,
                            minWidth: 150,
                            background: "var(--bg-elevated)",
                            border: "1px solid var(--border)",
                            borderRadius: "var(--radius)",
                            boxShadow: "var(--shadow-lg)",
                            padding: 4,
                            display: "flex",
                            flexDirection: "column",
                          }}
                        >
                          <button
                            role="menuitem"
                            type="button"
                            disabled={duplicatingId === pipeline.id}
                            onClick={() => void handleDuplicate(pipeline)}
                            style={{
                              textAlign: "left",
                              padding: "8px 10px",
                              background: "none",
                              border: "none",
                              borderRadius: "var(--radius-sm)",
                              color: "var(--text)",
                              cursor: "pointer",
                              fontSize: 13,
                            }}
                          >
                            Duplicar pipeline
                          </button>
                          <button
                            role="menuitem"
                            type="button"
                            onClick={() => {
                              setOpenMenuId(null);
                              setDeletingPipeline(pipeline);
                            }}
                            style={{
                              textAlign: "left",
                              padding: "8px 10px",
                              background: "none",
                              border: "none",
                              borderRadius: "var(--radius-sm)",
                              color: "var(--error)",
                              cursor: "pointer",
                              fontSize: 13,
                            }}
                          >
                            Excluir pipeline
                          </button>
                        </div>
                      )}
                    </div>
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

      <Modal
        open={!!deletingPipeline}
        title="Excluir pipeline"
        onClose={() => {
          if (!deleteBusy) setDeletingPipeline(null);
        }}
        footer={
          <>
            <Button disabled={deleteBusy} onClick={() => setDeletingPipeline(null)}>
              Cancelar
            </Button>
            <Button loading={deleteBusy} onClick={() => void handleDelete()}>
              Excluir
            </Button>
          </>
        }
      >
        <p>Excluir o pipeline {deletingPipeline?.name}? Esta ação não pode ser desfeita.</p>
      </Modal>
    </div>
  );
}
