"use client";

import * as React from "react";
import Link from "next/link";
import { Monitor, ArrowRight } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import type { BadgeStatus } from "@/components/ui/badge";
import type { PipelineRun } from "@/lib/types";

/**
 * Lista de runs recentes do dashboard (escopo fe-dashboard).
 * Cada run: pipeline, status (badge), início. Link → /pipelines/{id}/run.
 * Estados: loading (skeleton), vazio (EmptyState), cheio (lista).
 */

export interface RecentRunItem {
  run: PipelineRun;
  pipelineName?: string;
}

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

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export interface RecentRunsProps {
  items: RecentRunItem[];
  loading?: boolean;
  /** Atualiza o status de um run em tempo real (WS pipeline:status). */
  onRunStatusChange?: (pipelineId: string, runId: string, status: PipelineRun["status"]) => void;
}

export function RecentRuns({ items, loading = false }: RecentRunsProps) {
  if (loading) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        {[0, 1, 2].map((i) => (
          <Card key={i} style={{ minHeight: 64 }}>
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <Skeleton width={140} height={14} />
              <Skeleton width={90} height={14} />
              <Skeleton width={110} height={14} />
            </div>
          </Card>
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <EmptyState
        icon={Monitor}
        title="Nenhuma execução ainda"
        description="Quando uma pipeline for executada, os runs aparecem aqui em tempo real."
      />
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
      {items.map(({ run, pipelineName }) => (
        <Link
          key={run.id}
          href={`/pipelines/${run.pipelineId}/run`}
          aria-label={`Abrir monitor da pipeline ${pipelineName ?? run.pipelineId}`}
          style={{ display: "block", textDecoration: "none", color: "inherit" }}
        >
          <Card hoverable style={{ minHeight: 64 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "12px",
                flexWrap: "wrap",
              }}
            >
              <span
                aria-hidden="true"
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: "var(--radius-sm)",
                  background: "var(--bg-hover)",
                  color: "var(--text-secondary)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                }}
              >
                <Monitor size={14} aria-hidden="true" />
              </span>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div
                  style={{
                    fontSize: "12px",
                    fontWeight: 600,
                    color: "var(--text)",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {pipelineName ?? run.pipelineId}
                </div>
                <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                  Início: {formatDateTime(run.startedAt)}
                </div>
              </div>
              <Badge
                status={RUN_STATUS_BADGE[run.status]}
                label={RUN_STATUS_LABEL[run.status]}
                pulse={run.status === "running"}
              />
              <ArrowRight
                size={14}
                aria-hidden="true"
                style={{ color: "var(--text-muted)", flexShrink: 0 }}
              />
            </div>
          </Card>
        </Link>
      ))}
    </div>
  );
}
