"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { GitBranch, Plus, RefreshCw, AlertTriangle } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Pipeline, PaginatedResponse } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
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

export default function PipelinesPage() {
  const router = useRouter();
  const { addToast } = useToast();

  const [pipelines, setPipelines] = React.useState<Pipeline[]>([]);
  const [total, setTotal] = React.useState(0);
  const [page, setPage] = React.useState(1);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [creating, setCreating] = React.useState(false);

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
      router.push(`/pipelines/${res.id}`);
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
            {pipelines.map((pipeline) => (
              <button
                key={pipeline.id}
                onClick={() => router.push(`/pipelines/${pipeline.id}`)}
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
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
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
              </button>
            ))}
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
