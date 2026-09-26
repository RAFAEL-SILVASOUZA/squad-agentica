"use client";

import * as React from "react";
import Link from "next/link";
import {
  CheckCircle2,
  XCircle,
  MessageSquare,
  X,
  Monitor,
  RefreshCw,
  AlertTriangle,
  FileText,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api";
import type { ApprovalRequest } from "@/lib/types";

/**
 * Extensão local: o backend retorna `nodeId` (spec §4.5) mas o tipo
 * `ApprovalRequest` em lib/types.ts (dono: fe-shell) ainda não o inclui.
 * Registre a promoção de `nodeId` para lib/types.ts na resposta final.
 */
interface ApprovalRequestWithNode extends ApprovalRequest {
  nodeId?: string;
}

/**
 * ApprovalPanel (fe-approvals, design system §3.6).
 * Fila de aprovações pendentes + histórico.
 * - Cards com contexto: pipeline, nó de origem, output a aprovar, quando chegou.
 * - Ações: aprovar, rejeitar, argumentar (textarea obrigatório), cancelar.
 * - 409 (already_responded) → toast "Já respondida".
 * - Link para o monitor do run correspondente.
 * - Estados: loading (skeleton), vazio (EmptyState), erro (retry).
 */

export interface ApprovalPanelProps {
  /**
   * Callback opcional chamado quando a contagem de pendentes muda.
   * Usado pelo layout do dashboard para atualizar o badge da sidebar/topbar.
   */
  onPendingCountChange?: (count: number) => void;
}

type ApprovalStatus = "pending" | "approved" | "rejected" | "revised" | "cancelled";

interface ApprovalCardState {
  approval: ApprovalRequest;
  expanded: boolean;
  argument: string;
  responding: boolean;
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

function isUrgent(approval: ApprovalRequestWithNode): boolean {
  const ctx = approval.context as Record<string, unknown>;
  return ctx.urgent === true || ctx.priority === "high";
}

function getOutputSummary(approval: ApprovalRequestWithNode): string {
  const ctx = approval.context as Record<string, unknown>;
  if (ctx.output) return String(ctx.output);
  if (ctx.data && typeof ctx.data === "object") {
    const keys = Object.keys(ctx.data as Record<string, unknown>);
    if (keys.length > 0) return keys.join(", ");
  }
  return "";
}

export function ApprovalPanel({ onPendingCountChange }: ApprovalPanelProps) {
  const { addToast } = useToast();
  const [approvals, setApprovals] = React.useState<ApprovalRequestWithNode[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [expandedId, setExpandedId] = React.useState<string | null>(null);
  const [argument, setArgument] = React.useState("");
  const [respondingId, setRespondingId] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.list<ApprovalRequestWithNode>("/api/approvals", {
        page: 1,
        limit: 50,
        query: { status: "pending" },
      });
      setApprovals(res.items);
      onPendingCountChange?.(res.items.length);
    } catch (e) {
      const message =
        e instanceof Error ? e.message : "Falha ao carregar aprovações";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [onPendingCountChange]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const handleRespond = React.useCallback(
    async (approvalId: string, decision: "approved" | "rejected" | "revised", response: string | null) => {
      setRespondingId(approvalId);
      try {
        await api.post(`/api/approvals/${approvalId}/respond`, {
          decision,
          response,
        });
        // Remove da lista local (sai da fila de pendentes).
        setApprovals((prev) => {
          const next = prev.filter((a) => a.id !== approvalId);
          onPendingCountChange?.(next.length);
          return next;
        });
        setExpandedId(null);
        setArgument("");
        const label =
          decision === "approved"
            ? "Aprovação aprovada"
            : decision === "rejected"
              ? "Aprovação rejeitada"
              : "Argumento enviado";
        addToast("success", label);
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          addToast("warning", "Já respondida ou run cancelado");
          // Remove da lista local para sincronizar.
          setApprovals((prev) => {
            const next = prev.filter((a) => a.id !== approvalId);
            onPendingCountChange?.(next.length);
            return next;
          });
        } else {
          const message =
            e instanceof Error ? e.message : "Erro ao responder";
          addToast("error", message);
        }
      } finally {
        setRespondingId(null);
      }
    },
    [addToast, onPendingCountChange]
  );

  const handleCancel = React.useCallback(
    async (approvalId: string) => {
      setRespondingId(approvalId);
      try {
        await api.delete(`/api/approvals/${approvalId}`);
        setApprovals((prev) => {
          const next = prev.filter((a) => a.id !== approvalId);
          onPendingCountChange?.(next.length);
          return next;
        });
        addToast("info", "Aprovação cancelada");
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          addToast("warning", "Já respondida ou run cancelado");
          setApprovals((prev) => {
            const next = prev.filter((a) => a.id !== approvalId);
            onPendingCountChange?.(next.length);
            return next;
          });
        } else {
          const message =
            e instanceof Error ? e.message : "Erro ao cancelar";
          addToast("error", message);
        }
      } finally {
        setRespondingId(null);
      }
    },
    [addToast, onPendingCountChange]
  );

  const toggleExpand = React.useCallback((approvalId: string) => {
    setExpandedId((prev) => (prev === approvalId ? null : approvalId));
    setArgument("");
  }, []);

  // ─── Loading ──────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        {[0, 1, 2].map((i) => (
          <Card key={i} style={{ minHeight: 80 }}>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "auto 1fr auto",
                gap: "16px",
                alignItems: "center",
              }}
            >
              <Skeleton width={40} height={40} borderRadius="var(--radius-sm)" />
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                <Skeleton width="60%" height={14} />
                <Skeleton width="40%" height={12} />
              </div>
              <div style={{ display: "flex", gap: "8px" }}>
                <Skeleton width={70} height={30} />
                <Skeleton width={70} height={30} />
              </div>
            </div>
          </Card>
        ))}
      </div>
    );
  }

  // ─── Error ────────────────────────────────────────────────────────────────
  if (error) {
    return (
      <Card>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "12px",
            flexWrap: "wrap",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <AlertTriangle
              size={16}
              aria-hidden="true"
              style={{ color: "var(--error)" }}
            />
            <span style={{ fontSize: "13px", color: "var(--error)" }}>
              {error}
            </span>
          </div>
          <Button size="sm" onClick={() => void load()}>
            <RefreshCw size={13} aria-hidden="true" />
            Tentar novamente
          </Button>
        </div>
      </Card>
    );
  }

  // ─── Empty ────────────────────────────────────────────────────────────────
  if (approvals.length === 0) {
    return (
      <EmptyState
        icon={CheckCircle2}
        title="Nenhuma aprovação pendente"
        description="Quando um agente precisar de aprovação humana, o pedido aparece aqui."
      />
    );
  }

  // ─── List ─────────────────────────────────────────────────────────────────
  return (
    <div
      className="approvals-list"
      style={{ display: "flex", flexDirection: "column", gap: "12px" }}
    >
      {approvals.map((approval) => {
        const urgent = isUrgent(approval);
        const expanded = expandedId === approval.id;
        const responding = respondingId === approval.id;
        const outputSummary = getOutputSummary(approval);

        return (
          <div
            key={approval.id}
            data-approval-card={approval.id}
            data-urgent={urgent ? "true" : "false"}
            style={{
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
              borderLeft: urgent ? "3px solid var(--warning)" : "1px solid var(--border)",
              borderRadius: "var(--radius)",
              padding: "18px",
              display: "grid",
              gridTemplateColumns: expanded ? "auto 1fr" : "auto 1fr auto",
              gridTemplateRows: expanded ? "auto auto" : "auto",
              gap: "16px",
              alignItems: expanded ? "start" : "center",
              transition: "border-color var(--transition)",
            }}
          >
            {/* Icon */}
            <div
              aria-hidden="true"
              style={{
                width: 40,
                height: 40,
                borderRadius: "var(--radius-sm)",
                background: "var(--accent-subtle)",
                color: "var(--accent)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              <FileText size={16} aria-hidden="true" />
            </div>

            {/* Info */}
            <div style={{ minWidth: 0 }}>
              <div
                style={{
                  fontSize: "13px",
                  fontWeight: 600,
                  color: "var(--text)",
                  marginBottom: "4px",
                }}
              >
                {approval.message}
              </div>
              <div
                style={{
                  fontSize: "12px",
                  color: "var(--text-muted)",
                  display: "flex",
                  flexWrap: "wrap",
                  gap: "8px",
                  alignItems: "center",
                }}
              >
                <span>
                  Pipeline <code style={{ fontFamily: "var(--font-mono)", fontSize: "11px" }}>{approval.pipelineId}</code>
                </span>
                <span aria-hidden="true">·</span>
                <span>
                  Nó <code style={{ fontFamily: "var(--font-mono)", fontSize: "11px" }}>{approval.nodeId}</code>
                </span>
                {outputSummary && (
                  <>
                    <span aria-hidden="true">·</span>
                    <span>{outputSummary}</span>
                  </>
                )}
                <span aria-hidden="true">·</span>
                <span>{timeSince(approval.sentAt)}</span>
              </div>

              {/* Expanded: argument textarea */}
              {expanded && (
                <div style={{ marginTop: "12px" }}>
                  <Textarea
                    id={`argument-${approval.id}`}
                    label="Argumento"
                    placeholder="Descreva o que precisa mudar antes de aprovar..."
                    value={argument}
                    onChange={(e) => setArgument(e.target.value)}
                    rows={3}
                    disabled={responding}
                  />
                </div>
              )}
            </div>

            {/* Actions */}
            <div
              style={{
                display: "flex",
                gap: "8px",
                flexWrap: "wrap",
                ...(expanded
                  ? { gridColumn: "1 / -1", justifyContent: "flex-end" }
                  : {}),
              }}
            >
              {expanded ? (
                <>
                  <Button
                    size="sm"
                    onClick={() =>
                      void handleRespond(approval.id, "revised", argument.trim() || null)
                    }
                    disabled={responding || !argument.trim()}
                    loading={responding}
                    style={{
                      background: "var(--accent)",
                      borderColor: "var(--accent)",
                      color: "#fff",
                    }}
                  >
                    Enviar argumento
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => toggleExpand(approval.id)}
                    disabled={responding}
                  >
                    <X size={13} aria-hidden="true" />
                    Fechar
                  </Button>
                </>
              ) : (
                <>
                  <Button
                    size="sm"
                    onClick={() => void handleRespond(approval.id, "approved", null)}
                    disabled={responding}
                    loading={responding}
                    style={{
                      background: "var(--success)",
                      borderColor: "var(--success)",
                      color: "#fff",
                    }}
                  >
                    <CheckCircle2 size={13} aria-hidden="true" />
                    Aprovar
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => toggleExpand(approval.id)}
                    disabled={responding}
                  >
                    <MessageSquare size={13} aria-hidden="true" />
                    Argumentar
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => void handleRespond(approval.id, "rejected", null)}
                    disabled={responding}
                    loading={responding}
                    style={{
                      background: "var(--error)",
                      borderColor: "var(--error)",
                      color: "#fff",
                    }}
                  >
                    <XCircle size={13} aria-hidden="true" />
                    Rejeitar
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => void handleCancel(approval.id)}
                    disabled={responding}
                    aria-label={`Cancelar aprovação ${approval.id}`}
                  >
                    <X size={13} aria-hidden="true" />
                    Cancelar
                  </Button>
                </>
              )}
            </div>

            {/* Monitor link (always visible, below actions when expanded) */}
            <div
              style={{
                gridColumn: expanded ? "1 / -1" : undefined,
                display: "flex",
                justifyContent: "flex-end",
              }}
            >
              <Link
                href={`/pipelines/${approval.pipelineId}/run`}
                aria-label={`Ver monitor do run da pipeline ${approval.pipelineId}`}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "4px",
                  fontSize: "11px",
                  color: "var(--text-muted)",
                  transition: "color var(--transition)",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.color = "var(--accent)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = "var(--text-muted)";
                }}
              >
                <Monitor size={12} aria-hidden="true" />
                Monitor
              </Link>
            </div>
          </div>
        );
      })}
    </div>
  );
}
