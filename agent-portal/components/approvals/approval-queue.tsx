"use client";

import * as React from "react";
import Link from "next/link";
import { CheckCircle2, XCircle, MessageSquare, X, Monitor, AlertTriangle, FileText, HelpCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { Modal } from "@/components/ui/modal";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api";
import { getWebSocketClient, disposeWebSocketClient } from "@/lib/websocket";
import type { ApprovalRequest, ApprovalNewEvent, ApprovalResolvedEvent } from "@/lib/types";

interface ApprovalRequestWithNode extends ApprovalRequest {
  nodeId?: string;
  runId?: string | null;
}

export interface ApprovalQueueProps {
  /** Filtro de status: "pending" (padrão) ou "resolved". */
  status?: "pending" | "resolved";
  /** Filtra por pipelineId. */
  pipelineId?: string;
  onPendingCountChange?: (count: number) => void;
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

const CONTEXT_META_KEYS = new Set(["urgent", "priority", "_action"]);

function getReviewEntries(approval: ApprovalRequestWithNode): [string, string][] {
  const ctx = (approval.context ?? {}) as Record<string, unknown>;
  return Object.entries(ctx)
    .filter(([k, v]) => !CONTEXT_META_KEYS.has(k) && v !== null && v !== undefined && v !== "")
    .map(([k, v]) => [k, typeof v === "string" ? v : JSON.stringify(v, null, 2)]);
}

function isUrgent(approval: ApprovalRequestWithNode): boolean {
  const ctx = approval.context as Record<string, unknown>;
  return ctx.urgent === true || ctx.priority === "high";
}

interface RunFile {
  path: string;
  status: "added" | "modified" | "deleted" | null;
}

const FILE_STATUS_LABEL: Record<string, string> = { added: "novo", modified: "alterado", deleted: "removido" };

function ChangedFiles({ runId, pipelineId }: { runId: string; pipelineId: string }) {
  const [files, setFiles] = React.useState<RunFile[]>([]);
  React.useEffect(() => {
    let cancelled = false;
    api
      .get<{ items?: RunFile[] }>(`/api/runs/${runId}/files`)
      .then((res) => {
        if (!cancelled) setFiles((res?.items ?? []).filter((f) => f.status != null));
      })
      .catch(() => {
        if (!cancelled) setFiles([]);
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  if (files.length === 0) return null;
  return (
    <div style={{ marginTop: "10px" }}>
      <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "4px" }}>
        Arquivos alterados
      </div>
      <ul style={{ margin: 0, padding: 0, listStyle: "none", fontSize: "12px", fontFamily: "var(--font-mono)" }}>
        {files.map((f) => (
          <li key={f.path} style={{ display: "flex", gap: 8 }}>
            <span style={{ color: "var(--text-muted)", minWidth: 56 }}>{FILE_STATUS_LABEL[f.status as string]}</span>
            <span>{f.path}</span>
          </li>
        ))}
      </ul>
      <Link
        href={`/pipelines/${pipelineId}/run?tab=arquivos`}
        style={{ fontSize: "11px", color: "var(--accent)" }}
      >
        Ver arquivos no monitor
      </Link>
    </div>
  );
}

function ActionWithHint({ hint, children }: { hint: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 2 }}>
      {children}
      <span style={{ fontSize: "10px", color: "var(--text-muted)" }}>{hint}</span>
    </div>
  );
}

export function ApprovalQueue({ status = "pending", pipelineId, onPendingCountChange }: ApprovalQueueProps) {
  const { addToast } = useToast();
  const [approvals, setApprovals] = React.useState<ApprovalRequestWithNode[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [expandedId, setExpandedId] = React.useState<string | null>(null);
  const [argument, setArgument] = React.useState("");
  const [respondingId, setRespondingId] = React.useState<string | null>(null);
  const [rejectingId, setRejectingId] = React.useState<string | null>(null);
  const [helpOpen, setHelpOpen] = React.useState(false);
  const [cancellingId, setCancellingId] = React.useState<string | null>(null);

  const [names, setNames] = React.useState<{ pipelines: Record<string, string>; agents: Record<string, string> }>({ pipelines: {}, agents: {} });
  const namesLoaded = React.useRef(false);
  const loadNames = React.useCallback(async () => {
    if (namesLoaded.current) return;
    namesLoaded.current = true;
    const [p, a] = await Promise.allSettled([
      api.list<{ id: string; name: string }>("/api/pipelines", { page: 1, limit: 100 }),
      api.list<{ id: string; name: string }>("/api/agents", { page: 1, limit: 100 }),
    ]);
    const toMap = (r: typeof p) =>
      r.status === "fulfilled" && Array.isArray(r.value?.items)
        ? Object.fromEntries(r.value.items.filter((i) => i?.id && i?.name).map((i) => [i.id, i.name]))
        : {};
    setNames({ pipelines: toMap(p), agents: toMap(a) });
  }, []);

  React.useEffect(() => {
    if (!loading) onPendingCountChange?.(approvals.length);
  }, [approvals.length, loading, onPendingCountChange]);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const query: Record<string, string> = { status };
      if (pipelineId) query.pipelineId = pipelineId;
      const res = await api.list<ApprovalRequestWithNode>("/api/approvals", { page: 1, limit: 50, query });
      setApprovals(res.items);
      if (res.items.length > 0) void loadNames();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao carregar aprovações");
    } finally {
      setLoading(false);
    }
  }, [status, pipelineId, loadNames]);

  React.useEffect(() => { void load(); }, [load]);

  const handleRespond = React.useCallback(
    async (approvalId: string, decision: "approved" | "rejected" | "revised", response: string | null) => {
      setRespondingId(approvalId);
      try {
        await api.post(`/api/approvals/${approvalId}/respond`, { decision, response });
        setApprovals((prev) => prev.filter((a) => a.id !== approvalId));
        setExpandedId(null);
        setArgument("");
        const label = decision === "approved" ? "Aprovação aprovada. Pipeline retomada." : decision === "rejected" ? "Aprovação rejeitada. Pipeline cancelada neste ramo." : "Argumento enviado. Pipeline retomada com feedback.";
        addToast("success", label);
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          addToast("warning", "Já respondida ou run cancelado");
          setApprovals((prev) => prev.filter((a) => a.id !== approvalId));
        } else {
          addToast("error", e instanceof Error ? e.message : "Erro ao responder");
        }
      } finally {
        setRespondingId(null);
      }
    },
    [addToast]
  );

  // WebSocket (só para pending).
  React.useEffect(() => {
    if (status !== "pending") return;
    let cancelled = false;
    let wsClient: ReturnType<typeof getWebSocketClient> | null = null;
    let onNew: ((eventData: Record<string, unknown>) => void) | null = null;
    let onResolved: ((eventData: Record<string, unknown>) => void) | null = null;
    const connect = async () => {
      try {
        const tokenRes = await fetch("/api/session-token", { method: "GET", credentials: "same-origin" });
        if (!tokenRes.ok) return;
        const { accessToken } = (await tokenRes.json()) as { accessToken: string };
        wsClient = getWebSocketClient(accessToken);
        onNew = async (eventData: Record<string, unknown>) => {
          const event = eventData as unknown as ApprovalNewEvent;
          if (!event.approvalId) return;
          try {
            const fresh = await api.get<ApprovalRequestWithNode>(`/api/approvals/${event.approvalId}`);
            if (cancelled) return;
            setApprovals((prev) => (prev.some((a) => a.id === fresh.id) ? prev : [fresh, ...prev]));
          } catch { void load(); }
        };
        onResolved = (eventData: Record<string, unknown>) => {
          const event = eventData as unknown as ApprovalResolvedEvent;
          if (!event.approvalId) return;
          setApprovals((prev) => prev.filter((a) => a.id !== event.approvalId));
        };
        wsClient.on("approval:new", onNew);
        wsClient.on("approval:resolved", onResolved);
        wsClient.onReconnect(() => { void load(); });
        wsClient.connect();
      } catch { /* WS indisponível */ }
    };
    void connect();
    return () => {
      cancelled = true;
      if (wsClient && onNew) wsClient.off("approval:new", onNew);
      if (wsClient && onResolved) wsClient.off("approval:resolved", onResolved);
      disposeWebSocketClient();
    };
  }, [status, load]);

  const toggleExpand = React.useCallback((approvalId: string) => {
    setExpandedId((prev) => (prev === approvalId ? null : approvalId));
    setArgument("");
  }, []);

  const handleCancel = React.useCallback(
    async (approvalId: string) => {
      setCancellingId(approvalId);
      try {
        await api.delete(`/api/approvals/${approvalId}`);
        setApprovals((prev) => prev.filter((a) => a.id !== approvalId));
        addToast("info", "Aprovação cancelada");
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          addToast("warning", "Já respondida ou run cancelado");
          setApprovals((prev) => prev.filter((a) => a.id !== approvalId));
        } else {
          addToast("error", e instanceof Error ? e.message : "Erro ao cancelar");
        }
      } finally {
        setCancellingId(null);
      }
    },
    [addToast]
  );

  if (loading) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        {[0, 1, 2].map((i) => (
          <Card key={i} style={{ minHeight: 80 }}>
            <div style={{ display: "grid", gridTemplateColumns: "auto 1fr auto", gap: "16px", alignItems: "center" }}>
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

  if (error) {
    return (
      <Card>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px", flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <AlertTriangle size={16} aria-hidden="true" style={{ color: "var(--error)" }} />
            <span style={{ fontSize: "13px", color: "var(--error)" }}>{error}</span>
          </div>
          <Button size="sm" onClick={() => void load()}>
            <RefreshCw size={13} aria-hidden="true" />
            Tentar novamente
          </Button>
        </div>
      </Card>
    );
  }

  if (approvals.length === 0) {
    return (
      <>
        <EmptyState
          icon={CheckCircle2}
          title={status === "pending" ? "Nenhuma aprovação pendente" : "Nenhuma aprovação respondida"}
          description={status === "pending" ? "Quando um agente precisar de aprovação humana, o pedido aparece aqui." : "As aprovações que você responder aparecem aqui."}
          action={
            <button
              type="button"
              onClick={() => setHelpOpen(true)}
              style={{ display: "inline-flex", alignItems: "center", gap: "6px", fontSize: "13px", color: "var(--accent)", background: "none", border: "none", cursor: "pointer" }}
            >
              <HelpCircle size={14} aria-hidden="true" />
              Como funcionam as aprovações?
            </button>
          }
        />
        <Modal open={helpOpen} title="Como funcionam as aprovações?" onClose={() => setHelpOpen(false)}>
          <div style={{ display: "flex", flexDirection: "column", gap: "12px", fontSize: "13px", color: "var(--text-secondary)" }}>
            <p><strong style={{ color: "var(--text)" }}>Aprovar</strong> — a pipeline segue para o próximo agente com a saída atual.</p>
            <p><strong style={{ color: "var(--text)" }}>Argumentar</strong> — você escreve um feedback que segue para o próximo agente junto com a saída. A pipeline continua.</p>
            <p><strong style={{ color: "var(--text)" }}>Rejeitar</strong> — o agente anterior refaz o trabalho. A pipeline é cancelada neste ramo e recomeça do nó que gerou a aprovação.</p>
          </div>
        </Modal>
      </>
    );
  }

  return (
    <>
      <div className="approvals-list" style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        {approvals.map((approval) => {
          const urgent = isUrgent(approval);
          const expanded = expandedId === approval.id;
          const responding = respondingId === approval.id;
          const reviewEntries = getReviewEntries(approval);
          const pipelineName = names.pipelines[approval.pipelineId];
          const agentName = approval.agentId ? names.agents[approval.agentId] : undefined;

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
              }}
            >
              <div aria-hidden="true" style={{ width: 40, height: 40, borderRadius: "var(--radius-sm)", background: "var(--accent-subtle)", color: "var(--accent)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <FileText size={16} aria-hidden="true" />
              </div>

              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: "13px", fontWeight: 600, color: "var(--text)", marginBottom: "4px" }}>
                  {approval.message}
                </div>
                <div style={{ fontSize: "12px", color: "var(--text-muted)", display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "center" }}>
                  <span>
                    Pipeline{" "}
                    {pipelineName ? <strong>{pipelineName}</strong> : <code style={{ fontFamily: "var(--font-mono)", fontSize: "11px" }}>{approval.pipelineId}</code>}
                  </span>
                  {agentName && (<><span aria-hidden="true">·</span><span>Nó: <strong>{agentName}</strong></span></>)}
                  <span aria-hidden="true">·</span>
                  <span>{timeSince(approval.sentAt)}</span>
                </div>

                {reviewEntries.length > 0 && (
                  <div style={{ marginTop: "10px", display: "flex", flexDirection: "column", gap: "8px" }}>
                    {reviewEntries.map(([key, value]) => (
                      <div key={key}>
                        <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "4px" }}>{key}</div>
                        <pre
                          aria-label={`Conteúdo para revisão: ${key}`}
                          style={{ margin: 0, maxHeight: "72px", overflow: "hidden", padding: "10px 12px", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", fontSize: "12px", lineHeight: 1.5, whiteSpace: "pre-wrap", wordBreak: "break-word", fontFamily: "var(--font-mono)", color: "var(--text)" }}
                        >
                          {value}
                        </pre>
                      </div>
                    ))}
                  </div>
                )}

                {expanded && (
                  <div style={{ marginTop: "12px" }}>
                    <Textarea
                      id={`argument-${approval.id}`}
                      label="Argumento"
                      placeholder="Orientação para o próximo agente..."
                      hint="O conteúdo segue para o próximo agente junto com este feedback."
                      value={argument}
                      onChange={(e) => setArgument(e.target.value)}
                      rows={3}
                      disabled={responding}
                    />
                  </div>
                )}
              </div>

              <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", ...(expanded ? { gridColumn: "1 / -1", justifyContent: "flex-end" } : {}) }}>
                {expanded ? (
                  <>
                    <Button size="sm" onClick={() => void handleRespond(approval.id, "revised", argument.trim() || null)} disabled={responding || !argument.trim()} loading={responding} style={{ background: "var(--accent)", borderColor: "var(--accent)", color: "#fff" }}>
                      Enviar argumento
                    </Button>
                    <Button size="sm" onClick={() => toggleExpand(approval.id)} disabled={responding}>
                      <X size={13} aria-hidden="true" /> Fechar
                    </Button>
                  </>
                ) : (
                  <>
                    <ActionWithHint hint="Segue para o próximo agente">
                      <Button size="sm" onClick={() => void handleRespond(approval.id, "approved", null)} disabled={responding} loading={responding} style={{ background: "var(--success-strong)", borderColor: "var(--success-strong)", color: "#fff" }}>
                        <CheckCircle2 size={13} aria-hidden="true" /> Aprovar
                      </Button>
                    </ActionWithHint>
                    <ActionWithHint hint="Segue com o seu feedback">
                      <Button size="sm" onClick={() => toggleExpand(approval.id)} disabled={responding}>
                        <MessageSquare size={13} aria-hidden="true" /> Argumentar
                      </Button>
                    </ActionWithHint>
                    <ActionWithHint hint="O agente anterior refaz">
                      <Button size="sm" onClick={() => setRejectingId(approval.id)} disabled={responding} style={{ background: "var(--error-strong)", borderColor: "var(--error-strong)", color: "#fff" }}>
                        <XCircle size={13} aria-hidden="true" /> Rejeitar
                      </Button>
                    </ActionWithHint>
                    <Button size="sm" onClick={() => void handleCancel(approval.id)} disabled={responding || cancellingId !== null} loading={cancellingId === approval.id} aria-label={`Cancelar aprovação ${approval.id}`}>
                      <X size={13} aria-hidden="true" /> Cancelar
                    </Button>
                  </>
                )}
              </div>

              {approval.runId && <ChangedFiles runId={approval.runId} pipelineId={approval.pipelineId} />}

              <div style={{ gridColumn: expanded ? "1 / -1" : undefined, display: "flex", justifyContent: "flex-end", gap: "8px" }}>
                {approval.nodeId ? (
                  <Link
                    href={`/pipelines/${approval.pipelineId}/run?tab=resultado&node=${approval.nodeId}`}
                    aria-label={`Ver contexto do nó ${approval.nodeId}`}
                    style={{ display: "inline-flex", alignItems: "center", gap: "4px", fontSize: "11px", color: "var(--text-muted)" }}
                  >
                    <Monitor size={12} aria-hidden="true" />
                    Ver contexto
                  </Link>
                ) : (
                  <Link
                    href={`/pipelines/${approval.pipelineId}/run`}
                    aria-label={`Ver monitor do run da pipeline ${approval.pipelineId}`}
                    style={{ display: "inline-flex", alignItems: "center", gap: "4px", fontSize: "11px", color: "var(--text-muted)" }}
                  >
                    <Monitor size={12} aria-hidden="true" />
                    Monitor
                  </Link>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Modal de confirmação de rejeitar */}
      <Modal
        open={!!rejectingId}
        title="Confirmar rejeição"
        onClose={() => setRejectingId(null)}
        footer={
          <>
            <Button onClick={() => setRejectingId(null)} disabled={respondingId !== null}>Cancelar</Button>
            <Button
              onClick={() => { if (rejectingId) void handleRespond(rejectingId, "rejected", null); setRejectingId(null); }}
              loading={respondingId !== null}
              style={{ background: "var(--error-strong)", borderColor: "var(--error-strong)", color: "#fff" }}
            >
              Rejeitar
            </Button>
          </>
        }
      >
        <p>Rejeitar esta aprovação? O agente anterior refaz o trabalho e a pipeline é cancelada neste ramo.</p>
      </Modal>

      {/* Modal de ajuda */}
      <Modal open={helpOpen} title="Como funcionam as aprovações?" onClose={() => setHelpOpen(false)}>
        <div style={{ display: "flex", flexDirection: "column", gap: "12px", fontSize: "13px", color: "var(--text-secondary)" }}>
          <p><strong style={{ color: "var(--text)" }}>Aprovar</strong> — a pipeline segue para o próximo agente com a saída atual.</p>
          <p><strong style={{ color: "var(--text)" }}>Argumentar</strong> — você escreve um feedback que segue para o próximo agente junto com a saída. A pipeline continua.</p>
          <p><strong style={{ color: "var(--text)" }}>Rejeitar</strong> — o agente anterior refaz o trabalho. A pipeline é cancelada neste ramo e recomeça do nó que gerou a aprovação.</p>
        </div>
      </Modal>
    </>
  );
}
