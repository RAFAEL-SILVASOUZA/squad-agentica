"use client";

import * as React from "react";
import { renderInlineMarkdown } from "@/lib/inline-markdown";
import { Send, Square, Sparkles, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import { sendAgentChat } from "@/lib/agent-chat";
import type { Agent } from "@/lib/types";

/**
 * Chat de construção de agentes (spec §10).
 *
 * - Streaming SSE: a resposta do assistente é exibida token a token.
 * - Cancelamento: botão "Parar" aborta o stream (AbortController).
 * - 429 (rate limit, spec §14.1): desabilita o envio por retryAfter segundos.
 * - config_update: propaga a configuração atualizada para o preview.
 *
 * Sem emojis; ícones via lucide-react.
 */

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

export interface AgentChatProps {
  /** "/api/agents/chat" (novo) ou "/api/agents/{id}/chat" (edição). */
  chatPath: string;
  /** draftId da sessão (continua a conversa). */
  draftId: string | null;
  /** Chamado quando o stream termina com um draftId. */
  onDraftId?: (draftId: string) => void;
  /** Chamado a cada config_update com a configuração parcial. */
  onConfigUpdate?: (config: Partial<Agent>) => void;
  /** Mensagem inicial do assistente (boas-vindas). */
  initialAssistantMessage?: string;
  /** Chamado quando o streaming começa/termina (para o preview). */
  onStreamingChange?: (streaming: boolean) => void;
}

let msgCounter = 0;
function nextId(): string {
  msgCounter += 1;
  return `msg-${Date.now()}-${msgCounter}`;
}

export function AgentChat({
  chatPath,
  draftId,
  onDraftId,
  onConfigUpdate,
  initialAssistantMessage,
  onStreamingChange,
}: AgentChatProps) {
  const { addToast } = useToast();
  const [messages, setMessages] = React.useState<ChatMessage[]>(() =>
    initialAssistantMessage
      ? [{ id: nextId(), role: "assistant", content: initialAssistantMessage }]
      : []
  );
  const [input, setInput] = React.useState("");
  const [streaming, setStreaming] = React.useState(false);
  const [rateLimitedUntil, setRateLimitedUntil] = React.useState<number | null>(null);
  const [cooldown, setCooldown] = React.useState(0);

  // Propaga o estado de streaming para o preview (spec §10).
  React.useEffect(() => {
    onStreamingChange?.(streaming);
  }, [streaming, onStreamingChange]);

  const abortRef = React.useRef<AbortController | null>(null);
  const scrollRef = React.useRef<HTMLDivElement>(null);

  // Cooldown do rate limit: decrementa a cada segundo.
  React.useEffect(() => {
    if (rateLimitedUntil === null) return;
    if (Date.now() >= rateLimitedUntil) {
      setRateLimitedUntil(null);
      setCooldown(0);
      return;
    }
    setCooldown(Math.ceil((rateLimitedUntil - Date.now()) / 1000));
    const timer = setTimeout(() => {
      setCooldown((c) => c - 1);
    }, 1000);
    return () => clearTimeout(timer);
  }, [rateLimitedUntil, cooldown]);

  // Auto-scroll para a última mensagem.
  React.useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, streaming]);

  const appendAssistant = React.useCallback(
    (text: string) => {
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last && last.role === "assistant") {
          return [...prev.slice(0, -1), { ...last, content: last.content + text }];
        }
        return [...prev, { id: nextId(), role: "assistant", content: text }];
      });
    },
    []
  );

  const handleSend = React.useCallback(async () => {
    const text = input.trim();
    if (!text || streaming || rateLimitedUntil !== null) return;

    setInput("");
    setMessages((prev) => [
      ...prev,
      { id: nextId(), role: "user", content: text },
    ]);
    setStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const result = await sendAgentChat(
        chatPath,
        text,
        draftId,
        {
          onText: appendAssistant,
          onConfigUpdate: (config) => onConfigUpdate?.(config),
          onValidationError: (errors) => {
            addToast("warning", "Contrato do agente precisa de ajustes.");
            void errors;
          },
          onDone: (id) => {
            if (id) onDraftId?.(id);
          },
          onError: (err) => {
            addToast("error", err.message || "Falha no chat de construção.");
          },
        },
        controller.signal
      );

      if (result.rateLimited) {
        const seconds = result.retryAfter ?? 30;
        setRateLimitedUntil(Date.now() + seconds * 1000);
        setCooldown(seconds);
        addToast(
          "warning",
          `Limite de mensagens atingido. Tente novamente em ${seconds}s.`
        );
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }, [
    input,
    streaming,
    rateLimitedUntil,
    chatPath,
    draftId,
    appendAssistant,
    onConfigUpdate,
    onDraftId,
    addToast,
  ]);

  const handleCancel = React.useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  const disabled = streaming || rateLimitedUntil !== null || input.trim() === "";

  return (
    <Card style={{ display: "flex", flexDirection: "column", minHeight: 320 }}>
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "10px",
          padding: "12px 14px",
          borderBottom: "1px solid var(--border)",
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
          <Sparkles size={15} aria-hidden="true" />
        </span>
        <div>
          <div style={{ fontSize: "13px", fontWeight: 600, color: "var(--text)" }}>
            Construção do Agente
          </div>
          <div style={{ fontSize: "11px", color: "var(--text-secondary)" }}>
            IA assistente
          </div>
        </div>
      </div>

      {/* Mensagens */}
      <div
        ref={scrollRef}
        role="log"
        aria-label="Mensagens do chat"
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "14px",
          display: "flex",
          flexDirection: "column",
          gap: "10px",
          maxHeight: 420,
        }}
      >
        {messages.length === 0 && (
          <div
            style={{
              fontSize: "12px",
              color: "var(--text-muted)",
              textAlign: "center",
              padding: "24px 8px",
            }}
          >
            Descreva o que o agente deve fazer para começar.
          </div>
        )}
        {messages.map((msg) => (
          <div
            key={msg.id}
            style={{
              alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
              maxWidth: "85%",
              padding: "8px 12px",
              borderRadius: "var(--radius-sm)",
              background:
                msg.role === "user" ? "var(--accent)" : "var(--bg-elevated)",
              color: msg.role === "user" ? "#fff" : "var(--text)",
              fontSize: "13px",
              lineHeight: 1.5,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              border:
                msg.role === "assistant" ? "1px solid var(--border)" : "none",
            }}
          >
            {msg.role === "assistant" ? renderInlineMarkdown(msg.content) : msg.content}
          </div>
        ))}
        {streaming && (
          <div
            style={{
              alignSelf: "flex-start",
              fontSize: "11px",
              color: "var(--text-muted)",
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            <span
              aria-hidden="true"
              style={{
                width: 10,
                height: 10,
                border: "2px solid var(--text-muted)",
                borderTopColor: "transparent",
                borderRadius: "50%",
                display: "inline-block",
                animation: "spin 1s linear infinite",
              }}
            />
            Assistente respondendo…
          </div>
        )}
      </div>

      {/* Aviso de validação */}
      {rateLimitedUntil !== null && (
        <div
          role="alert"
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
            padding: "8px 14px",
            fontSize: "12px",
            color: "var(--warning)",
            borderTop: "1px solid var(--border)",
          }}
        >
          <AlertTriangle size={13} aria-hidden="true" />
          Limite de mensagens atingido. Tente novamente em {cooldown}s.
        </div>
      )}

      {/* Input */}
      <div
        style={{
          display: "flex",
          gap: "8px",
          padding: "12px 14px",
          borderTop: "1px solid var(--border)",
        }}
      >
        <label htmlFor="agent-chat-input" style={{ position: "absolute", left: -9999 }}>
          Mensagem
        </label>
        <input
          id="agent-chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Descreva o que o agente deve fazer…"
          disabled={streaming || rateLimitedUntil !== null}
          style={{
            flex: 1,
            padding: "10px 14px",
            borderRadius: "var(--radius-sm)",
            border: "1px solid var(--border)",
            background: "var(--bg-elevated)",
            color: "var(--text)",
            fontSize: "13px",
            fontFamily: "var(--font)",
            outline: "none",
            opacity: streaming || rateLimitedUntil !== null ? 0.6 : 1,
          }}
        />
        {streaming ? (
          <Button size="sm" onClick={handleCancel} aria-label="Parar resposta">
            <Square size={13} aria-hidden="true" />
            Parar
          </Button>
        ) : (
          <Button
            size="sm"
            variant="primary"
            onClick={() => void handleSend()}
            disabled={disabled}
            aria-label="Enviar mensagem"
          >
            <Send size={13} aria-hidden="true" />
            Enviar
          </Button>
        )}
      </div>
    </Card>
  );
}
