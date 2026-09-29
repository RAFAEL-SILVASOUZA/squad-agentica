"use client";

import * as React from "react";
import { ArrowLeft, ExternalLink, GitBranch, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { Pipeline, PipelineRun } from "@/lib/types";
import { RUN_STATUS_BADGE, RUN_STATUS_LABEL } from "./status";

export interface RunHeaderProps {
  pipeline: Pipeline;
  run: PipelineRun | null;
  /** Nova tentativa de publicar o PR (POST /api/runs/{id}/publish). */
  onPublish: () => void;
  /** Botões de ação do run (iniciar, pausar, ...), montados pelo contêiner. */
  actions: React.ReactNode;
  publishing?: boolean;
}

const alertStyle: React.CSSProperties = {
  display: "flex",
  gap: 8,
  alignItems: "flex-start",
  flexWrap: "wrap",
  padding: "10px 14px",
  marginBottom: 12,
  borderRadius: "var(--radius)",
  border: "1px solid var(--error)",
  background: "var(--error-bg)",
  color: "var(--text)",
  fontSize: 12,
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
};

const mutedChip: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 4,
  fontSize: 11,
  color: "var(--text-muted)",
};

/**
 * Cabeçalho do monitor: nome, status do run, repositório, resultado da
 * publicação (link do PR / "Nenhum arquivo alterado" / falha com nova
 * tentativa) e as ações do run.
 */
export function RunHeader({ pipeline, run, onPublish, actions, publishing = false }: RunHeaderProps) {
  const publishStatus = run?.publishStatus ?? "none";

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          marginBottom: 12,
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
          <Button size="sm" onClick={() => window.history.back()} aria-label="Voltar">
            <ArrowLeft size={14} aria-hidden="true" />
          </Button>
          <div style={{ minWidth: 0 }}>
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
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 4, flexWrap: "wrap" }}>
              {run && (
                <>
                  <Badge
                    status={RUN_STATUS_BADGE[run.status]}
                    label={RUN_STATUS_LABEL[run.status]}
                    pulse={run.status === "running"}
                  />
                  <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                    Iniciado: {new Date(run.startedAt).toLocaleString("pt-BR")}
                  </span>
                </>
              )}
              <span style={mutedChip}>
                <GitBranch size={11} aria-hidden="true" />
                {pipeline.repository ? pipeline.repository.fullName : "Sem repositório"}
              </span>
              {run && publishStatus === "published" && run.prUrl && (
                <a
                  href={run.prUrl}
                  target="_blank"
                  rel="noreferrer"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 4,
                    fontSize: 12,
                    fontWeight: 600,
                    color: "var(--accent)",
                  }}
                >
                  {run.prNumber != null ? `PR #${run.prNumber}` : "Pull Request"}
                  <ExternalLink size={11} aria-hidden="true" />
                </a>
              )}
              {run && publishStatus === "no_changes" && (
                <span style={mutedChip}>Nenhum arquivo alterado</span>
              )}
              {run && run.status === "completed" && pipeline.repository && publishStatus === "none" && (
                // Run concluído com repositório mas sem publicação (ex.: o
                // repositório foi configurado depois): publicar manualmente.
                <Button size="sm" onClick={onPublish} loading={publishing}>
                  <GitBranch size={12} aria-hidden="true" />
                  Publicar
                </Button>
              )}
            </div>
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>{actions}</div>
      </div>

      {run?.status === "failed" && run.error && (
        <div role="alert" style={alertStyle}>
          <strong style={{ color: "var(--error)", flexShrink: 0 }}>Falha na execução:</strong>
          <span>{run.error}</span>
        </div>
      )}

      {run && publishStatus === "failed" && (
        <div role="alert" style={{ ...alertStyle, alignItems: "center" }}>
          <strong style={{ color: "var(--error)", flexShrink: 0 }}>Falha ao publicar o PR:</strong>
          <span style={{ flex: 1, minWidth: 160 }}>{run.publishError || "erro desconhecido"}</span>
          <Button size="sm" onClick={onPublish} loading={publishing}>
            <RotateCcw size={12} aria-hidden="true" />
            Tentar publicar de novo
          </Button>
        </div>
      )}
    </div>
  );
}
