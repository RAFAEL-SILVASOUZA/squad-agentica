"use client";

import * as React from "react";
import { Select } from "@/components/ui/select";

export interface LogEntry {
  id: string;
  nodeId: string;
  level: string;
  message: string;
  at: string;
}

export interface LogsTabProps {
  logs: LogEntry[];
  /** Agentes da pipeline (nó → nome), para o filtro e o rótulo da linha. */
  agents: { nodeId: string; name: string }[];
}

const LOG_LEVEL_COLORS: Record<string, string> = {
  debug: "var(--text-muted)",
  info: "var(--info)",
  warn: "var(--warning)",
  error: "var(--error)",
};

/**
 * Aba Logs em largura total, com filtros por agente e por nível
 * (info/warn/error) e auto-scroll pausável.
 */
export function LogsTab({ logs, agents }: LogsTabProps) {
  const [agentFilter, setAgentFilter] = React.useState("all");
  const [levelFilter, setLevelFilter] = React.useState("all");
  const [autoScroll, setAutoScroll] = React.useState(true);
  const containerRef = React.useRef<HTMLDivElement>(null);

  const names = React.useMemo(() => new Map(agents.map((a) => [a.nodeId, a.name])), [agents]);

  const filtered = React.useMemo(
    () =>
      logs.filter(
        (log) =>
          (agentFilter === "all" || log.nodeId === agentFilter) &&
          (levelFilter === "all" || log.level === levelFilter)
      ),
    [logs, agentFilter, levelFilter]
  );

  React.useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [filtered, autoScroll]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <div style={{ flex: "1 1 200px", maxWidth: 280 }}>
          <Select
            aria-label="Filtrar por agente"
            value={agentFilter}
            onValueChange={setAgentFilter}
            options={[
              { value: "all", label: "Todos os agentes" },
              ...agents.map((a) => ({ value: a.nodeId, label: a.name })),
            ]}
          />
        </div>
        <div style={{ flex: "1 1 160px", maxWidth: 220 }}>
          <Select
            aria-label="Filtrar por nível"
            value={levelFilter}
            onValueChange={setLevelFilter}
            options={[
              { value: "all", label: "Todos os níveis" },
              { value: "info", label: "Info" },
              { value: "warn", label: "Warn" },
              { value: "error", label: "Error" },
            ]}
          />
        </div>
        <button
          type="button"
          onClick={() => setAutoScroll(!autoScroll)}
          aria-label={autoScroll ? "Desativar auto-scroll" : "Ativar auto-scroll"}
          aria-pressed={autoScroll}
          style={{
            marginLeft: "auto",
            background: "none",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)",
            padding: "6px 10px",
            fontSize: 11,
            fontWeight: 600,
            textTransform: "uppercase",
            color: autoScroll ? "var(--accent)" : "var(--text-muted)",
            cursor: "pointer",
          }}
        >
          Auto-scroll
        </button>
      </div>

      <div
        ref={containerRef}
        role="log"
        aria-label="Logs da execução"
        style={{
          height: "calc(100vh - 340px)",
          minHeight: 320,
          overflowY: "auto",
          background: "var(--bg-elevated)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-sm)",
          padding: 10,
          fontFamily: "var(--font-mono)",
          fontSize: 12,
          lineHeight: 1.6,
        }}
      >
        {filtered.length === 0 ? (
          <div style={{ padding: 12, color: "var(--text-muted)", textAlign: "center" }}>
            {logs.length === 0 ? "Aguardando logs da execução…" : "Nenhum log corresponde ao filtro."}
          </div>
        ) : (
          filtered.map((log) => (
            <div
              key={log.id}
              style={{
                display: "flex",
                gap: 10,
                padding: "2px 0",
                borderBottom: "1px solid var(--border-subtle)",
              }}
            >
              <span style={{ color: "var(--text-muted)", flexShrink: 0, whiteSpace: "nowrap" }}>
                {new Date(log.at).toLocaleTimeString("pt-BR")}
              </span>
              <span
                style={{
                  color: LOG_LEVEL_COLORS[log.level] ?? "var(--text-secondary)",
                  fontWeight: 600,
                  flexShrink: 0,
                  textTransform: "uppercase",
                  fontSize: 10,
                  minWidth: 42,
                  paddingTop: 2,
                }}
              >
                {log.level}
              </span>
              <span
                style={{
                  color: "var(--text-secondary)",
                  flexShrink: 0,
                  width: 140,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={names.get(log.nodeId) ?? log.nodeId}
              >
                {names.get(log.nodeId) ?? log.nodeId}
              </span>
              <span style={{ color: "var(--text)", wordBreak: "break-word", whiteSpace: "pre-wrap", minWidth: 0 }}>
                {log.message}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
