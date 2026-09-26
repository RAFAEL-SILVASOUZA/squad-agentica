"use client";

import * as React from "react";

/**
 * Badge de status (design system §2.6).
 * Dot 7px + rótulo. Variantes por estado.
 */
export type BadgeStatus =
  | "success"
  | "warning"
  | "error"
  | "info"
  | "neutral"
  | "running"
  | "pending"
  | "completed"
  | "failed"
  | "paused"
  | "stopped"
  | "cancelled"
  | "approved"
  | "rejected"
  | "revised"
  | "deployed"
  | "draft"
  | "archived"
  | "connected"
  | "disconnected";

const STATUS_COLORS: Record<BadgeStatus, string> = {
  success: "var(--success)",
  warning: "var(--warning)",
  error: "var(--error)",
  info: "var(--info)",
  neutral: "var(--text-muted)",
  running: "var(--info)",
  pending: "var(--warning)",
  completed: "var(--success)",
  failed: "var(--error)",
  paused: "var(--warning)",
  stopped: "var(--text-muted)",
  cancelled: "var(--text-muted)",
  approved: "var(--success)",
  rejected: "var(--error)",
  revised: "var(--info)",
  deployed: "var(--success)",
  draft: "var(--warning)",
  archived: "var(--text-muted)",
  connected: "var(--success)",
  disconnected: "var(--text-muted)",
};

export interface BadgeProps {
  status: BadgeStatus;
  label?: string;
  pulse?: boolean;
}

export function Badge({ status, label, pulse = false }: BadgeProps) {
  const color = STATUS_COLORS[status] ?? "var(--text-muted)";

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "6px",
        fontSize: "12px",
        color: "var(--text-secondary)",
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 7,
          height: 7,
          borderRadius: "50%",
          background: color,
          display: "inline-block",
          animation: pulse ? "pulse 2s ease-in-out infinite" : undefined,
        }}
      />
      {label && <span>{label}</span>}
    </span>
  );
}
