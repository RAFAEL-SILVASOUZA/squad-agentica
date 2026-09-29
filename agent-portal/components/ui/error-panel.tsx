"use client";

import * as React from "react";
import { AlertTriangle, Copy } from "lucide-react";

/**
 * Painel de erro com recuperação (regra de UX do redesign).
 * Mostra o impacto na linguagem do usuário + ação de recuperação; os
 * detalhes técnicos ficam recolhidos atrás de "Ver detalhes".
 */
export interface ErrorPanelProps {
  /** O que o usuário não conseguiu fazer, ex.: "Não foi possível salvar o agente" */
  title: string;
  /** Detalhes técnicos (código HTTP, endpoint, log), ex.: "HTTP 404 · POST /api/agents" */
  detail?: string;
  /** Ação de recuperação principal; quando ausente, não renderiza o botão. */
  onRetry?: () => void;
  /** Rótulo do botão de recuperação. */
  retryLabel?: string;
  /** Ações alternativas renderizadas ao lado da recuperação. */
  actions?: React.ReactNode;
}

const btnBase: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "6px",
  borderRadius: "var(--radius-sm)",
  fontSize: "13px",
  fontWeight: 500,
  padding: "8px 16px",
  fontFamily: "var(--font)",
  cursor: "pointer",
  border: "1px solid var(--border)",
  transition: "background var(--transition), border-color var(--transition)",
};

export function ErrorPanel({
  title,
  detail,
  onRetry,
  retryLabel = "Tentar de novo",
  actions,
}: ErrorPanelProps) {
  const [open, setOpen] = React.useState(false);
  const [copied, setCopied] = React.useState(false);

  const copyDetail = React.useCallback(() => {
    if (!detail) return;
    navigator.clipboard
      ?.writeText(detail)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      })
      .catch(() => {});
  }, [detail]);

  return (
    <div
      role="alert"
      style={{
        border: "1px solid var(--error)",
        borderRadius: "var(--radius)",
        padding: "14px 16px",
        background: "var(--bg-card)",
        display: "flex",
        flexDirection: "column",
        gap: "10px",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: "10px",
          color: "var(--text)",
          fontSize: "13px",
          fontWeight: 600,
        }}
      >
        <AlertTriangle size={16} aria-hidden="true" style={{ color: "var(--error)", flexShrink: 0, marginTop: 1 }} />
        <span>{title}</span>
      </div>

      {detail ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          <div style={{ display: "flex", gap: "8px" }}>
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              aria-expanded={open}
              style={{ ...btnBase, background: "none", color: "var(--text-secondary)", padding: "4px 8px" }}
            >
              {open ? "Ocultar detalhes" : "Ver detalhes"}
            </button>
            <button
              type="button"
              onClick={copyDetail}
              style={{ ...btnBase, background: "none", color: "var(--text-secondary)", padding: "4px 8px" }}
            >
              <Copy size={13} aria-hidden="true" />
              {copied ? "Copiado" : "Copiar detalhes"}
            </button>
          </div>
          {/* Mantido no DOM recolhido (display:none), senão leitores de
              tela perderiam o detalhe ao trocar o estado */}
          <pre
            className="mono"
            hidden={!open}
            style={{
              margin: 0,
              padding: "8px 10px",
              borderRadius: "var(--radius-sm)",
              background: "var(--bg-elevated)",
              border: "1px solid var(--border)",
              color: "var(--text-secondary)",
              overflowX: "auto",
              fontSize: "12px",
            }}
          >
            {detail}
          </pre>
        </div>
      ) : null}

      {(onRetry || actions) && (
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          {onRetry ? (
            <button
              type="button"
              onClick={onRetry}
              style={{ ...btnBase, background: "var(--accent)", border: "1px solid var(--accent)", color: "#fff" }}
            >
              {retryLabel}
            </button>
          ) : null}
          {actions}
        </div>
      )}
    </div>
  );
}
