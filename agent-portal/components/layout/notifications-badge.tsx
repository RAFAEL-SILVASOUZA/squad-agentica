"use client";

import * as React from "react";

/**
 * Badge de notificações (design system §2.14).
 * Pill com contagem de aprovações pendentes.
 * Consumido pelo AppTopbar e pela sidebar.
 * O nó fe-approvals estende este componente para consumir WS approval:new.
 */
export interface NotificationsBadgeProps {
  count: number;
  onClick?: () => void;
}

export function NotificationsBadge({ count, onClick }: NotificationsBadgeProps) {
  if (count <= 0) return null;

  return (
    <button
      onClick={onClick}
      aria-label={`${count} aprovações pendentes`}
      style={{
        fontSize: "10px",
        fontWeight: 600,
        background: "var(--accent)",
        color: "#fff",
        borderRadius: "10px",
        padding: "1px 6px",
        minWidth: 18,
        textAlign: "center",
        border: "none",
        cursor: "pointer",
        display: "inline-block",
      }}
    >
      {count > 99 ? "99+" : count}
    </button>
  );
}
