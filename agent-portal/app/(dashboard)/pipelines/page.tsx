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
 * Portal starts empty (contract §0): empty state with "Create first pipeline" CTA.
 */
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
        setError(err.message);
      } else {
        setError("Failed to load pipelines");
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
        name: "New Pipeline",
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
        addToast("error", "Failed to create pipeline");
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
            Manage your agent pipelines
          </p>
        </div>
        <Button
          variant="primary"
          onClick={handleCreate}
          disabled={creating}
          aria-label="Create new pipeline"
        >
          <Plus size={14} aria-hidden="true" />
          {creating ? "Creating..." : "New Pipeline"}
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
              Failed to load pipelines
            </div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{error}</div>
          </div>
          <Button
            size="sm"
            onClick={() => fetchPipelines(page)}
            aria-label="Retry loading pipelines"
          >
            <RefreshCw size={12} aria-hidden="true" />
            Retry
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
          title="No pipelines yet"
          description="Create your first pipeline to orchestrate agents."
          action={
            <Button
              variant="primary"
              onClick={handleCreate}
              disabled={creating}
              aria-label="Create first pipeline"
            >
              <Plus size={14} aria-hidden="true" />
              Create first pipeline
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
                    label={pipeline.status}
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
                  <span>{pipeline.nodes.length} nodes</span>
                  <span>{pipeline.edges.length} edges</span>
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
                aria-label="Previous page"
              >
                Previous
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
                aria-label="Next page"
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
