"use client";

import * as React from "react";
import Link from "next/link";
import { CheckCircle2, ArrowRight } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import type { ApprovalRequest } from "@/lib/types";

/**
 * Lista de aprovações pendentes do dashboard (escopo fe-dashboard).
 * Cada item: mensagem, pipeline, tempo desde envio. Link → /approvals.
 * Estados: loading (skeleton), vazio (EmptyState), cheio (lista).
 */

export interface PendingApprovalsProps {
  items: ApprovalRequest[];
  loading?: boolean;
}

function timeSince(iso: string | null | undefined): string {
  if (!iso) return "agora";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "agora";
  const diffMs = Date.now() - date.getTime();
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "agora";
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `há ${hours} h`;
  const days = Math.floor(hours / 24);
  return `há ${days} d`;
}

export function PendingApprovals({ items, loading = false }: PendingApprovalsProps) {
  if (loading) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        {[0, 1].map((i) => (
          <Card key={i} style={{ minHeight: 64 }}>
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <Skeleton width={200} height={14} />
              <Skeleton width={80} height={14} />
            </div>
          </Card>
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <EmptyState
        icon={CheckCircle2}
        title="Nenhuma aprovação pendente"
        description="Quando um agente precisar de aprovação humana, o pedido aparece aqui."
      />
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
      {items.map((approval) => (
        <Link
          key={approval.id}
          href="/approvals"
          aria-label={`Abrir aprovações: ${approval.message}`}
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
                  background: "var(--accent-subtle)",
                  color: "var(--accent)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                }}
              >
                <CheckCircle2 size={14} aria-hidden="true" />
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
                  {approval.message}
                </div>
                <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                  Pipeline {approval.pipelineId} · {timeSince(approval.sentAt)}
                </div>
              </div>
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
