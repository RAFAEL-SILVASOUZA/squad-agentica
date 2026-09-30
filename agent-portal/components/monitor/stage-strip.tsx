"use client";

import * as React from "react";
import { ChevronRight, Shield } from "lucide-react";
import type { Pipeline } from "@/lib/types";
import { NODE_STATUS_LABEL, type NodeStatus } from "./status";

export interface Stage {
  /** Nó do agente; na aprovação, o nó de destino da aresta. */
  nodeId: string;
  name: string;
  status: NodeStatus;
  kind: "agent" | "approval";
  /** Chave única (a aprovação usa o id da aresta). */
  key: string;
}

export interface StageStripProps {
  steps: Stage[];
  onSelect: (nodeId: string) => void;
}

const STATUS_COLOR: Record<NodeStatus, string> = {
  pending: "var(--text-muted)",
  running: "var(--info)",
  completed: "var(--success)",
  failed: "var(--error)",
  waiting_approval: "var(--warning)",
};

/**
 * Ordem topológica a partir do nó de entrada (Kahn sobre as arestas; ciclos
 * de loop não travam — nós restantes seguem na ordem em que aparecem).
 */
export function orderNodes(pipeline: Pipeline): string[] {
  const ids = pipeline.nodes.map((n) => n.id);
  const known = new Set(ids);
  const indegree = new Map<string, number>(ids.map((id) => [id, 0]));
  const next = new Map<string, string[]>(ids.map((id) => [id, []]));
  for (const e of pipeline.edges) {
    if (!known.has(e.source) || !known.has(e.target) || e.source === e.target) continue;
    next.get(e.source)!.push(e.target);
    indegree.set(e.target, (indegree.get(e.target) ?? 0) + 1);
  }

  const order: string[] = [];
  const seen = new Set<string>();
  const entry = pipeline.entryNodeId && known.has(pipeline.entryNodeId) ? pipeline.entryNodeId : null;
  const queue: string[] = entry ? [entry] : [];
  for (const id of ids) if (id !== entry && indegree.get(id) === 0) queue.push(id);

  const visit = (q: string[]) => {
    while (q.length > 0) {
      const id = q.shift()!;
      if (seen.has(id)) continue;
      seen.add(id);
      order.push(id);
      for (const t of next.get(id) ?? []) {
        const d = (indegree.get(t) ?? 0) - 1;
        indegree.set(t, d);
        if (d <= 0 && !seen.has(t)) q.push(t);
      }
    }
  };
  visit(queue);
  // Ciclos: o primeiro nó pendente destrava o resto.
  for (const id of ids) if (!seen.has(id)) visit([id]);
  return order;
}

function approvalStatus(source?: NodeStatus, target?: NodeStatus): NodeStatus {
  if (source === "waiting_approval" || target === "waiting_approval") return "waiting_approval";
  if (target === "running" || target === "completed" || target === "failed") return "completed";
  return "pending";
}

/** Etapas do run: um chip por agente e por aresta com aprovação humana. */
export function buildStages(pipeline: Pipeline, statuses: Record<string, NodeStatus>): Stage[] {
  const byId = new Map(pipeline.nodes.map((n) => [n.id, n]));
  const stages: Stage[] = [];
  for (const id of orderNodes(pipeline)) {
    const node = byId.get(id)!;
    stages.push({
      nodeId: id,
      name: node.label ?? node.agentSnapshot.name,
      status: statuses[id] ?? "pending",
      kind: "agent",
      key: id,
    });
    for (const e of pipeline.edges) {
      if (e.source !== id || !e.requiresApproval) continue;
      stages.push({
        nodeId: e.target,
        name: "Aprovação",
        status: approvalStatus(statuses[e.source], statuses[e.target]),
        kind: "approval",
        key: `approval-${e.id}`,
      });
    }
  }
  return stages;
}

/** Faixa horizontal de etapas; clicar num agente foca o resultado dele. */
export function StageStrip({ steps, onSelect }: StageStripProps) {
  const listRef = React.useRef<HTMLOListElement>(null);
  const [overflowing, setOverflowing] = React.useState(false);

  const checkOverflow = React.useCallback(() => {
    const el = listRef.current;
    if (el) setOverflowing(el.scrollWidth > el.clientWidth);
  }, []);

  React.useEffect(() => {
    checkOverflow();
    const el = listRef.current;
    if (!el) return;
    el.addEventListener("scroll", checkOverflow);
    let ro: ResizeObserver | undefined;
    if (typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(checkOverflow);
      ro.observe(el);
    }
    return () => {
      el.removeEventListener("scroll", checkOverflow);
      ro?.disconnect();
    };
  }, [checkOverflow, steps.length]);

  const scrollToEnd = () => {
    const el = listRef.current;
    if (el) el.scrollTo({ left: el.scrollWidth, behavior: "smooth" });
  };

  return (
    <div style={{ position: "relative" }}>
      <ol
        ref={listRef}
        aria-label="Etapas"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          listStyle: "none",
          margin: 0,
          padding: "2px 0 6px",
          overflowX: "auto",
        }}
      >
        {steps.map((step, i) => {
          const color = STATUS_COLOR[step.status];
          const label = NODE_STATUS_LABEL[step.status];
          const chip: React.CSSProperties = {
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            padding: "5px 10px",
            borderRadius: 999,
            border: `1px solid ${step.status === "pending" ? "var(--border)" : color}`,
            background: "var(--bg-card)",
            color: "var(--text)",
            fontSize: 12,
            whiteSpace: "nowrap",
          };
          const dot = (
            <span
              aria-hidden="true"
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: color,
                flexShrink: 0,
                animation: step.status === "running" ? "pulse 1.5s infinite" : undefined,
              }}
            />
          );
          return (
            <li key={step.key} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              {i > 0 && <ChevronRight size={12} aria-hidden="true" style={{ color: "var(--text-muted)" }} />}
              {step.kind === "agent" ? (
                <button
                  type="button"
                  onClick={() => onSelect(step.nodeId)}
                  aria-label={`${step.name} — ${label}`}
                  title={label}
                  style={{ ...chip, cursor: "pointer" }}
                >
                  {dot}
                  {step.name}
                </button>
              ) : (
                <span style={{ ...chip, color: "var(--text-secondary)" }} title={`Aprovação — ${label}`}>
                  <Shield size={11} aria-hidden="true" style={{ color }} />
                  <span>Aprovação</span>
                </span>
              )}
            </li>
          );
        })}
      </ol>
      {overflowing && (
        <button
          type="button"
          onClick={scrollToEnd}
          aria-label="Mais etapas"
          style={{
            position: "absolute",
            right: 0,
            top: "50%",
            transform: "translateY(-50%)",
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
            padding: "4px 10px",
            fontSize: 11,
            fontWeight: 600,
            color: "var(--text-secondary)",
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderRadius: 999,
            cursor: "pointer",
            boxShadow: "0 2px 8px rgba(0,0,0,0.12)",
          }}
        >
          Mais etapas →
        </button>
      )}
    </div>
  );
}
