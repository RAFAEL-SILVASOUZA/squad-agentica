"use client";

import * as React from "react";
import { Check, ChevronDown, ChevronRight, Copy } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Markdown } from "@/components/ui/markdown";
import { NODE_STATUS_BADGE, NODE_STATUS_LABEL, type NodeStatus } from "./status";

export interface ResultStep {
  nodeId: string;
  name: string;
  status: NodeStatus;
  output: unknown;
}

export interface ResultsTabProps {
  steps: ResultStep[];
  /** Agente a trazer para a vista (clique na faixa de etapas ou no grafo). */
  focusNodeId?: string;
  /** Muda a cada pedido de foco, para rolar de novo ao mesmo agente. */
  focusKey?: number;
}

const PENDING_TEXT: Record<NodeStatus, string> = {
  pending: "Aguardando execução.",
  running: "Em execução…",
  waiting_approval: "Aguardando aprovação humana.",
  failed: "Este agente falhou. Veja os detalhes na aba Logs.",
  completed: "Concluído sem saída.",
};

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = React.useState(false);
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={() => {
        try {
          void Promise.resolve(navigator.clipboard?.writeText(text))
            .then(() => {
              setCopied(true);
              window.setTimeout(() => setCopied(false), 1500);
            })
            .catch(() => undefined);
        } catch {
          // Sem clipboard (contexto inseguro): nada a fazer.
        }
      }}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "3px 8px",
        fontSize: 11,
        color: copied ? "var(--success)" : "var(--text-muted)",
        background: "none",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-sm)",
        cursor: "pointer",
      }}
    >
      {copied ? <Check size={11} aria-hidden="true" /> : <Copy size={11} aria-hidden="true" />}
      {copied ? "Copiado" : "Copiar"}
    </button>
  );
}

function PortValue({ value }: { value: unknown }) {
  if (typeof value === "string") return <Markdown>{value}</Markdown>;
  return (
    <pre
      style={{
        margin: 0,
        padding: 10,
        fontFamily: "var(--font-mono)",
        fontSize: 12,
        background: "var(--bg-elevated)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-sm)",
        overflowX: "auto",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
      }}
    >
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function textOf(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function StepOutput({ output }: { output: unknown }) {
  if (typeof output === "string") {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <CopyButton text={output} label="Copiar saída" />
        </div>
        <Markdown>{output}</Markdown>
      </div>
    );
  }
  if (output && typeof output === "object" && !Array.isArray(output)) {
    // `_action` é o controle de fluxo do agente, não conteúdo.
    const entries = Object.entries(output as Record<string, unknown>).filter(([k]) => k !== "_action");
    if (entries.length === 0) {
      return <p style={{ margin: 0, fontSize: 12, color: "var(--text-muted)" }}>Sem saída.</p>;
    }
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {entries.map(([port, value]) => (
          <div key={port}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 8,
                marginBottom: 8,
              }}
            >
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  color: "var(--text-secondary)",
                  textTransform: "uppercase",
                  letterSpacing: "0.5px",
                  fontFamily: "var(--font-mono)",
                }}
              >
                {port}
              </span>
              <CopyButton text={textOf(value)} label={`Copiar ${port}`} />
            </div>
            <PortValue value={value} />
          </div>
        ))}
      </div>
    );
  }
  return <PortValue value={output} />;
}

/**
 * Aba Resultado: a saída de cada agente, na ordem do grafo, em largura total
 * e renderizada como markdown (antes ficava espremida num painel lateral).
 */
export function ResultsTab({ steps, focusNodeId, focusKey }: ResultsTabProps) {
  const baseId = React.useId();
  const sectionRefs = React.useRef<Record<string, HTMLElement | null>>({});
  // Seções recolhidas (padrão: todas abertas).
  const [collapsed, setCollapsed] = React.useState<Set<string>>(() => new Set());

  const toggle = (nodeId: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(nodeId)) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });

  React.useEffect(() => {
    if (!focusNodeId) return;
    // Focar pela faixa de etapas (ou pelo grafo) reabre a seção recolhida.
    setCollapsed((prev) => {
      if (!prev.has(focusNodeId)) return prev;
      const next = new Set(prev);
      next.delete(focusNodeId);
      return next;
    });
    const el = sectionRefs.current[focusNodeId];
    if (el && typeof el.scrollIntoView === "function") {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [focusNodeId, focusKey]);

  if (steps.length === 0) {
    return <p style={{ fontSize: 13, color: "var(--text-muted)" }}>Nenhum agente nesta pipeline.</p>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {steps.map((step, i) => {
        const headingId = `${baseId}-step-${i}`;
        const bodyId = `${baseId}-body-${i}`;
        const focused = step.nodeId === focusNodeId;
        const open = !collapsed.has(step.nodeId);
        return (
          <section
            key={step.nodeId}
            ref={(el) => {
              sectionRefs.current[step.nodeId] = el;
            }}
            aria-labelledby={headingId}
            style={{
              scrollMarginTop: 16,
              padding: "16px 20px",
              background: "var(--bg-card)",
              border: `1px solid ${focused ? "var(--accent)" : "var(--border)"}`,
              borderRadius: "var(--radius)",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: open ? 12 : 0,
              }}
            >
              <button
                type="button"
                onClick={() => toggle(step.nodeId)}
                aria-expanded={open}
                aria-controls={bodyId}
                aria-label={`${open ? "Recolher" : "Expandir"} ${step.name}`}
                title={open ? "Recolher" : "Expandir"}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  padding: 2,
                  color: "var(--text-muted)",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                }}
              >
                {open ? <ChevronDown size={14} aria-hidden="true" /> : <ChevronRight size={14} aria-hidden="true" />}
              </button>
              <h2 id={headingId} style={{ margin: 0, flex: 1, fontSize: 14, fontWeight: 600, color: "var(--text)" }}>
                {step.name}
              </h2>
              <Badge
                status={NODE_STATUS_BADGE[step.status]}
                label={NODE_STATUS_LABEL[step.status]}
                pulse={step.status === "running"}
              />
            </div>
            <div id={bodyId} hidden={!open}>
              {open &&
                (step.output === undefined ? (
                  <p style={{ margin: 0, fontSize: 12, color: "var(--text-muted)" }}>{PENDING_TEXT[step.status]}</p>
                ) : (
                  <StepOutput output={step.output} />
                ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
