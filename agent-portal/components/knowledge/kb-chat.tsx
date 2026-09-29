"use client";

import * as React from "react";
import { MessageSquarePlus, Send, Trash2, RefreshCw, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Modal } from "@/components/ui/modal";
import { Markdown } from "@/components/ui/markdown";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api";
import type { ChatMessage, ChatSource, ConversationSummary } from "./types";

/**
 * KbChat: chat com a base de conhecimento e conversas salvas.
 * - Coluna de conversas (Nova conversa, título/data, excluir) + área de
 *   mensagens em bolhas (pergunta à direita, resposta em markdown à esquerda).
 * - Fontes numeradas e recolhíveis sob cada resposta.
 * - Enter envia, Shift+Enter quebra linha. Ao abrir, carrega a mais recente.
 * - A conversa só é criada no servidor ao enviar a 1ª pergunta.
 * - Em erro do LLM a pergunta já ficou salva: recarrega a conversa e oferece
 *   "Tentar de novo" (reenvia o mesmo texto).
 */
export interface KbChatProps {
  baseId: string;
}

interface ConversationDetail {
  id: string;
  title: string;
  messages: ChatMessage[];
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function SourceList({ sources }: { sources: ChatSource[] }) {
  if (!sources || sources.length === 0) return null;
  return (
    <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
      <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)" }}>Fontes</span>
      {sources.map((s, i) => (
        <details
          key={`${s.chunkId}-${i}`}
          style={{
            fontSize: 12,
            border: "1px solid var(--border-subtle)",
            borderRadius: "var(--radius-sm)",
            background: "var(--bg-card)",
            padding: "4px 8px",
          }}
        >
          <summary style={{ cursor: "pointer", color: "var(--text-secondary)" }}>
            {`${i + 1}. ${s.documentName}`} <span style={{ color: "var(--text-muted)" }}>· score {s.score.toFixed(2)}</span>
          </summary>
          <p style={{ margin: "6px 0 2px", color: "var(--text)", whiteSpace: "pre-wrap" }}>{s.text}</p>
        </details>
      ))}
    </div>
  );
}

export function KbChat({ baseId }: KbChatProps) {
  const { addToast } = useToast();
  const [conversations, setConversations] = React.useState<ConversationSummary[]>([]);
  const [activeId, setActiveId] = React.useState<string | null>(null);
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [input, setInput] = React.useState("");
  const [sending, setSending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [failedContent, setFailedContent] = React.useState<string | null>(null);
  const [deleting, setDeleting] = React.useState<ConversationSummary | null>(null);
  const [deleteBusy, setDeleteBusy] = React.useState(false);
  const bottomRef = React.useRef<HTMLDivElement>(null);
  const inputRef = React.useRef<HTMLTextAreaElement>(null);
  const wasSending = React.useRef(false);
  // Descarta respostas de carregamentos superados (troca rápida de conversa/base).
  const loadSeq = React.useRef(0);

  const base = `/api/knowledge/${baseId}/conversations`;

  const fetchList = React.useCallback(async (): Promise<ConversationSummary[]> => {
    const res = await api.get<{ items?: ConversationSummary[] }>(base);
    return res?.items ?? [];
  }, [base]);

  const openConversation = React.useCallback(
    async (id: string) => {
      const seq = ++loadSeq.current;
      setActiveId(id);
      setError(null);
      setFailedContent(null);
      try {
        const detail = await api.get<ConversationDetail>(`${base}/${id}`);
        if (seq !== loadSeq.current) return;
        setMessages(detail.messages ?? []);
      } catch (e) {
        if (seq !== loadSeq.current) return;
        setMessages([]);
        setError(e instanceof ApiError ? e.message : "Não foi possível carregar a conversa.");
      }
    },
    [base]
  );

  // Ao abrir a base: lista as conversas e carrega a mais recente.
  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setSending(false);
    setActiveId(null);
    setMessages([]);
    setError(null);
    setFailedContent(null);
    setInput("");
    void (async () => {
      try {
        const items = await fetchList();
        if (cancelled) return;
        setConversations(items);
        if (items.length > 0) await openConversation(items[0].id);
      } catch (e) {
        if (!cancelled) setError(e instanceof ApiError ? e.message : "Não foi possível carregar as conversas.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    const seqRef = loadSeq;
    return () => {
      cancelled = true;
      seqRef.current++;
    };
  }, [fetchList, openConversation]);

  // Devolve o foco ao campo quando o envio termina (ele fica desabilitado).
  React.useEffect(() => {
    if (wasSending.current && !sending) inputRef.current?.focus();
    wasSending.current = sending;
  }, [sending]);

  React.useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages, sending, error]);

  function newConversation() {
    loadSeq.current++;
    setActiveId(null);
    setMessages([]);
    setError(null);
    setFailedContent(null);
  }

  const send = React.useCallback(
    async (content: string, opts?: { retry?: boolean }) => {
      const text = content.trim();
      if (!text || sending) return;
      setSending(true);
      setError(null);
      setFailedContent(null);
      if (!opts?.retry) {
        setMessages((prev) => [...prev, { id: `local-${Date.now()}`, role: "user", content: text, sources: [] }]);
        setInput("");
      }
      // Se o usuário trocar de base/conversa durante o envio (loadSeq muda),
      // a resposta não pode escrever na visão da outra conversa.
      const seq = loadSeq.current;
      const stale = () => seq !== loadSeq.current;
      let cid = activeId;
      try {
        if (!cid) {
          const created = await api.post<{ id: string }>(base, {});
          cid = created.id;
          if (!stale()) setActiveId(cid);
        }
        const answer = await api.post<ChatMessage>(`${base}/${cid}/messages`, { content: text });
        if (stale()) return;
        setMessages((prev) => [...prev, { ...answer, sources: answer.sources ?? [] }]);
        try {
          const items = await fetchList();
          if (!stale()) setConversations(items);
        } catch {
          /* a lista é só informativa */
        }
      } catch (e) {
        if (stale()) return;
        setError(e instanceof ApiError ? e.message : "Não foi possível obter a resposta.");
        setFailedContent(text);
        if (cid) {
          // A pergunta já foi gravada no servidor: recarrega para exibi-la.
          try {
            const detail = await api.get<ConversationDetail>(`${base}/${cid}`);
            if (stale()) return;
            setMessages(detail.messages ?? []);
            const items = await fetchList();
            if (!stale()) setConversations(items);
          } catch {
            /* mantém a pergunta local */
          }
        }
      } finally {
        if (!stale()) setSending(false);
      }
    },
    [activeId, base, fetchList, sending]
  );

  async function confirmDelete() {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      await api.delete(`${base}/${deleting.id}`);
      const remaining = conversations.filter((c) => c.id !== deleting.id);
      setConversations(remaining);
      setDeleting(null);
      if (deleting.id === activeId) {
        if (remaining.length > 0) await openConversation(remaining[0].id);
        else newConversation();
      }
    } catch (e) {
      addToast("error", e instanceof ApiError ? e.message : "Erro ao excluir conversa");
    } finally {
      setDeleteBusy(false);
    }
  }

  return (
    <Card>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "stretch" }}>
        {/* Conversas */}
        <div style={{ flex: "1 1 200px", maxWidth: "100%", minWidth: 0, display: "flex", flexDirection: "column", gap: 8 }}>
          <Button size="sm" variant="primary" onClick={newConversation} disabled={sending}>
            <MessageSquarePlus size={14} aria-hidden="true" />
            Nova conversa
          </Button>
          <div
            aria-label="Conversas"
            className="kb-conv-list"
            style={{ display: "flex", flexDirection: "column", gap: 4, overflowY: "auto" }}
          >
            {conversations.length === 0 && !loading && (
              <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0 }}>Nenhuma conversa ainda.</p>
            )}
            {conversations.map((c) => (
              <div
                key={c.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                  borderRadius: "var(--radius-sm)",
                  border: c.id === activeId ? "1px solid var(--accent)" : "1px solid transparent",
                  background: c.id === activeId ? "var(--bg-elevated)" : "transparent",
                }}
              >
                <button
                  type="button"
                  onClick={() => void openConversation(c.id)}
                  disabled={sending}
                  aria-current={c.id === activeId ? "true" : undefined}
                  style={{
                    flex: 1,
                    minWidth: 0,
                    textAlign: "left",
                    background: "none",
                    border: "none",
                    padding: "6px 8px",
                    cursor: "pointer",
                    fontFamily: "var(--font)",
                  }}
                >
                  <span
                    style={{
                      display: "block",
                      fontSize: 13,
                      color: "var(--text)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {c.title}
                  </span>
                  <span style={{ display: "block", fontSize: 11, color: "var(--text-muted)" }}>{formatDate(c.updatedAt)}</span>
                </button>
                <button
                  type="button"
                  aria-label={`Excluir conversa ${c.title}`}
                  onClick={() => setDeleting(c)}
                  style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: 6 }}
                >
                  <Trash2 size={13} aria-hidden="true" />
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Mensagens */}
        <div style={{ flex: "999 1 360px", minWidth: 0, display: "flex", flexDirection: "column", gap: 12 }}>
          <div
            role="log"
            aria-label="Mensagens"
            style={{
              minHeight: 320,
              maxHeight: "60vh",
              overflowY: "auto",
              display: "flex",
              flexDirection: "column",
              gap: 12,
              padding: "4px 2px",
            }}
          >
            {!loading && messages.length === 0 && !sending && !error && (
              <p style={{ fontSize: 13, color: "var(--text-muted)", margin: "auto", textAlign: "center" }}>
                Pergunte algo sobre os documentos desta base.
              </p>
            )}
            {messages.map((m) =>
              m.role === "user" ? (
                <div
                  key={m.id}
                  style={{
                    alignSelf: "flex-end",
                    maxWidth: "85%",
                    background: "var(--accent)",
                    color: "#fff",
                    padding: "8px 12px",
                    borderRadius: "12px 12px 2px 12px",
                    fontSize: 13,
                    whiteSpace: "pre-wrap",
                    overflowWrap: "anywhere",
                  }}
                >
                  {m.content}
                </div>
              ) : (
                <div
                  key={m.id}
                  style={{
                    alignSelf: "flex-start",
                    maxWidth: "95%",
                    background: "var(--bg-elevated)",
                    color: "var(--text)",
                    padding: "8px 12px",
                    borderRadius: "12px 12px 12px 2px",
                    fontSize: 13,
                    overflowWrap: "anywhere",
                  }}
                >
                  <Markdown>{m.content}</Markdown>
                  <SourceList sources={m.sources} />
                </div>
              )
            )}
            {sending && (
              <div role="status" style={{ alignSelf: "flex-start", fontSize: 13, color: "var(--text-muted)" }}>
                Pensando…
              </div>
            )}
            {error && (
              <div
                role="alert"
                style={{ alignSelf: "flex-start", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", fontSize: 13, color: "var(--error)" }}
              >
                <AlertTriangle size={14} aria-hidden="true" />
                <span>{error}</span>
                {failedContent && (
                  <Button size="sm" onClick={() => void send(failedContent, { retry: true })} disabled={sending}>
                    <RefreshCw size={13} aria-hidden="true" />
                    Tentar de novo
                  </Button>
                )}
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
            <textarea
              ref={inputRef}
              aria-label="Mensagem"
              value={input}
              rows={2}
              placeholder="Pergunte algo… (Enter envia, Shift+Enter quebra linha)"
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent?.isComposing) {
                  e.preventDefault();
                  void send(input);
                }
              }}
              disabled={sending}
              style={{
                flex: 1,
                minWidth: 0,
                resize: "vertical",
                maxHeight: 200,
                padding: "8px 10px",
                fontSize: 13,
                fontFamily: "var(--font)",
                color: "var(--text)",
                background: "var(--bg-elevated)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
              }}
            />
            <Button variant="primary" onClick={() => void send(input)} disabled={sending || !input.trim()}>
              <Send size={14} aria-hidden="true" />
              Enviar
            </Button>
          </div>
        </div>
      </div>

      <Modal
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        title="Excluir conversa"
        footer={
          <>
            <Button size="sm" onClick={() => setDeleting(null)} disabled={deleteBusy}>
              Cancelar
            </Button>
            <Button
              size="sm"
              onClick={() => void confirmDelete()}
              loading={deleteBusy}
              style={{ background: "var(--error-strong)", borderColor: "var(--error-strong)", color: "#fff" }}
            >
              Excluir
            </Button>
          </>
        }
      >
        <p style={{ fontSize: 13, color: "var(--text)", margin: 0 }}>
          Excluir a conversa <strong>{deleting?.title}</strong>? As mensagens serão removidas.
        </p>
      </Modal>
    </Card>
  );
}
