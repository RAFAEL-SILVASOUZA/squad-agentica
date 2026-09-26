"use client";

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, AlertTriangle, RefreshCw, GitBranch } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Agent, Pipeline, PipelineNode, PipelineEdge } from "@/lib/types";
import { FlowEditor } from "@/components/FlowEditor";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { useToast } from "@/components/ui/toast";

/**
 * Pipeline detail page: renders the FlowEditor for a specific pipeline.
 *
 * Endpoints used:
 * - GET /api/pipelines/{id} — load pipeline graph
 * - PUT /api/pipelines/{id} — save graph (409 if run in progress)
 * - GET /api/agents — load available agents for the palette
 *
 * Extension point for fe-flow-edges:
 * - The `edgePanelSlot` prop on FlowEditor is where the EdgePanel will be rendered.
 * - `onEdgeSelect` callback provides the selected edge data.
 * - fe-flow-edges can import this page and add the EdgePanel component.
 */
export default function PipelineDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { addToast } = useToast();

  const pipelineId = params.id;

  const [pipeline, setPipeline] = React.useState<Pipeline | null>(null);
  const [agents, setAgents] = React.useState<Agent[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [notFound, setNotFound] = React.useState(false);

  // Selected edge (for fe-flow-edges EdgePanel)
  const [selectedEdge, setSelectedEdge] = React.useState<PipelineEdge | null>(null);

  const fetchPipeline = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [pipelineRes, agentsRes] = await Promise.all([
        api.get<Pipeline>(`/api/pipelines/${pipelineId}`),
        api.list<Agent>("/api/agents", { limit: 100 }),
      ]);
      setPipeline(pipelineRes);
      setAgents(agentsRes.items);
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
  }, [pipelineId]);

  React.useEffect(() => {
    fetchPipeline();
  }, [fetchPipeline]);

  // Save handler: PUT /api/pipelines/{id}
  const handleSave = React.useCallback(
    async (nodes: PipelineNode[], edges: PipelineEdge[]) => {
      if (!pipeline) return;

      const updated: Pipeline = {
        ...pipeline,
        nodes,
        edges,
        entryNodeId:
          pipeline.entryNodeId ||
          (nodes.length > 0 ? nodes[0].id : ""),
      };

      try {
        const res = await api.put<Pipeline>(`/api/pipelines/${pipelineId}`, updated);
        setPipeline(res);
      } catch (err) {
        if (err instanceof ApiError) {
          if (err.status === 409) {
            addToast("error", "Pipeline has a run in progress. Stop the run before editing.");
          } else {
            throw err;
          }
        } else {
          throw err;
        }
      }
    },
    [pipeline, pipelineId, addToast]
  );

  // Edge select handler (extension point for fe-flow-edges)
  const handleEdgeSelect = React.useCallback((edge: PipelineEdge | null) => {
    setSelectedEdge(edge);
  }, []);

  // Loading state
  if (loading) {
    return (
      <div>
        <div style={{ marginBottom: 16 }}>
          <Skeleton height={32} width={200} />
        </div>
        <Skeleton height="calc(100vh - 200px)" />
      </div>
    );
  }

  // Not found
  if (notFound) {
    return (
      <EmptyState
        icon={GitBranch}
        title="Pipeline not found"
        description="This pipeline does not exist or was deleted."
        action={
          <Button onClick={() => router.push("/pipelines")}>
            <ArrowLeft size={14} aria-hidden="true" />
            Back to pipelines
          </Button>
        }
      />
    );
  }

  // Error state
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
              Failed to load pipeline
            </div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{error}</div>
          </div>
          <Button
            size="sm"
            onClick={fetchPipeline}
            aria-label="Retry loading pipeline"
          >
            <RefreshCw size={12} aria-hidden="true" />
            Retry
          </Button>
        </div>
        <Button
          size="sm"
          onClick={() => router.push("/pipelines")}
        >
          <ArrowLeft size={12} aria-hidden="true" />
          Back to pipelines
        </Button>
      </div>
    );
  }

  if (!pipeline) return null;

  return (
    <div>
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 16,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Button
            size="sm"
            onClick={() => router.push("/pipelines")}
            aria-label="Back to pipelines"
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
            {pipeline.description && (
              <p
                style={{
                  fontSize: "var(--text-lg)",
                  color: "var(--text-secondary)",
                  margin: "2px 0 0",
                }}
              >
                {pipeline.description}
              </p>
            )}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Button
            size="sm"
            onClick={() => router.push(`/pipelines/${pipelineId}/run`)}
            aria-label="View pipeline monitor"
          >
            Monitor
          </Button>
        </div>
      </div>

      {/* Flow Editor */}
      <FlowEditor
        pipeline={pipeline}
        agents={agents}
        onSave={handleSave}
        onEdgeSelect={handleEdgeSelect}
        disabled={pipeline.status === "running"}
        {/*
          Extension point for fe-flow-edges:
          Pass edgePanelSlot={<EdgePanel edge={selectedEdge} ... />} here.
          The selectedEdge state is available via handleEdgeSelect.
        */}
      />
    </div>
  );
}
