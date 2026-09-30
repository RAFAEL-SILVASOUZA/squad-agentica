"use client";

import * as React from "react";
import Link from "next/link";
import { CheckCircle2, XCircle } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { SkeletonRows } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api";
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
  const { addToast } = useToast();
  const [respondingId, setRespondingId] = React.useState<string | null>(null);

  const handleRespond = React.useCallback(
    async (approvalId: string, decision: "approved" | "rejected") => {
      setRespondingId(approvalId);
      try {
        await api.post(`/api/approvals/${approvalId}/respond`, { decision, response: null });
        addToast("success", decision === "approved" ? "Aprovação aprovada." : "Aprovação rejeitada.");
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          addToast("warning", "Já respondida ou run cancelado");
        } else {
          addToast("error", e instanceof Error ? e.message : "Erro ao responder");
        }
      } finally {
        setRespondingId(null);
      }
    },
    [addToast]
  );

  if (loading) {
    return <SkeletonRows rows={2} height={64} gap={8} />;
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
        <Card key={approval.id} hoverable style={{ minHeight: 64 }}>
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
              <Link href="/approvals" style={{ textDecoration: "none", color: "inherit" }}>
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
              </Link>
              <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                Pipeline {approval.pipelineId} · {timeSince(approval.sentAt)}
              </div>
            </div>
            <div style={{ display: "flex", gap: "6px", flexShrink: 0 }}>
              <Button
                size="sm"
                onClick={() => void handleRespond(approval.id, "approved")}
                disabled={respondingId !== null}
                loading={respondingId === approval.id}
                style={{ background: "var(--success-strong)", borderColor: "var(--success-strong)", color: "#fff" }}
              >
                <CheckCircle2 size={12} aria-hidden="true" /> Aprovar
              </Button>
              <Button
                size="sm"
                onClick={() => void handleRespond(approval.id, "rejected")}
                disabled={respondingId !== null}
                style={{ background: "var(--error-strong)", borderColor: "var(--error-strong)", color: "#fff" }}
              >
                <XCircle size={12} aria-hidden="true" /> Rejeitar
              </Button>
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}
