"use client";

import * as React from "react";
import type { LucideIcon } from "lucide-react";

/**
 * Empty state (design system §2.17).
 * Container centralizado com ícone, título, descrição e CTA opcional.
 */
export interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "48px 24px",
        textAlign: "center",
        gap: "12px",
      }}
    >
      {Icon && (
        <Icon
          size={40}
          aria-hidden="true"
          style={{ color: "var(--text-muted)", opacity: 0.6 }}
        />
      )}
      <h3
        style={{
          fontSize: "14px",
          fontWeight: 600,
          color: "var(--text)",
          margin: 0,
        }}
      >
        {title}
      </h3>
      {description && (
        <p
          style={{
            fontSize: "12px",
            color: "var(--text-secondary)",
            margin: 0,
            maxWidth: 320,
          }}
        >
          {description}
        </p>
      )}
      {action && <div style={{ marginTop: "8px" }}>{action}</div>}
    </div>
  );
}
