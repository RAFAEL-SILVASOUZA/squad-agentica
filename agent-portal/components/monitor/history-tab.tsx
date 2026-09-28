"use client";

import * as React from "react";
import { Clock, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { Checkpoint, PipelineRun } from "@/lib/types";
import { RUN_STATUS_BADGE, RUN_STATUS_LABEL } from "./status";

export interface HistoryTabProps {
  runs: PipelineRun[];
  checkpoints: Checkpoint[];
  onResumeCheckpoint: (checkpointId: string) => void;
  /** Ação em andamento (`resume-cp-<id>` marca o botão como carregando). */
  actionLoading: string | null;
}

const row: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 8,
  padding: "8px 10px",
  background: "var(--bg-card)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-sm)",
};

/** Aba Histórico: runs anteriores e checkpoints (retomar de um checkpoint). */
export function HistoryTab({ runs, checkpoints, onResumeCheckpoint, actionLoading }: HistoryTabProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        {runs.length === 0 ? (
          <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0 }}>Nenhuma execução ainda.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {runs.map((run) => (
              <div key={run.id} style={row}>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 12, color: "var(--text)", fontWeight: 500 }}>
                    {new Date(run.startedAt).toLocaleString("pt-BR")}
                  </div>
                  {run.error && (
                    <div
                      style={{
                        fontSize: 11,
                        color: "var(--error)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                      title={run.error}
                    >
                      {run.error}
                    </div>
                  )}
                </div>
                {run.prUrl && (
                  <a
                    href={run.prUrl}
                    target="_blank"
                    rel="noreferrer"
                    style={{ fontSize: 11, color: "var(--accent)", flexShrink: 0 }}
                  >
                    {run.prNumber != null ? `PR #${run.prNumber}` : "Pull Request"}
                  </a>
                )}
                <Badge status={RUN_STATUS_BADGE[run.status]} label={RUN_STATUS_LABEL[run.status]} />
              </div>
            ))}
          </div>
        )}
      </div>

      {checkpoints.length > 0 && (
        <div>
          <div
            style={{
              fontSize: 12,
              color: "var(--text-muted)",
              marginBottom: 6,
              display: "flex",
              alignItems: "center",
              gap: 4,
            }}
          >
            <Clock size={12} aria-hidden="true" />
            Checkpoints
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {checkpoints.map((cp) => (
              <div key={cp.id} style={{ ...row, padding: "6px 10px", borderColor: "var(--border-subtle)" }}>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 12, color: "var(--text)" }}>
                    {new Date(cp.timestamp).toLocaleString("pt-BR")}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Nó: {cp.nodeId}</div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <Badge
                    status={cp.status === "completed" ? "completed" : cp.status === "interrupted" ? "paused" : "failed"}
                    label={cp.status === "completed" ? "Concluído" : cp.status === "interrupted" ? "Interrompido" : "Falhou"}
                  />
                  {(cp.status === "interrupted" || cp.status === "failed") && (
                    <Button
                      size="sm"
                      onClick={() => onResumeCheckpoint(cp.id)}
                      loading={actionLoading === `resume-cp-${cp.id}`}
                      aria-label={`Retomar do checkpoint ${cp.id}`}
                    >
                      <RotateCcw size={11} aria-hidden="true" />
                      Retomar
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
