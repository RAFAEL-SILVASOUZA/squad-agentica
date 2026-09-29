/**
 * Cliente do chat de construção de agentes (SSE).
 *
 * Consome os endpoints do nó be-agent-chat (spec §9.2 + §10):
 * - POST /api/agents/chat        → construção de novo agente (sessão efêmera)
 * - POST /api/agents/{id}/chat   → edição de agente existente
 * - POST /api/agents/chat/confirm → confirma o draft e salva o agente
 *
 * O stream SSE emite eventos no formato:
 *   data: { "type": "text" | "config_update" | "validation_error" | "done", "data": ... }
 *
 * Este módulo NÃO usa lib/api.ts para o stream (o fetch precisa de
 * streaming incremental + AbortController). Para o token, reutiliza o
 * mesmo endpoint GET /api/session-token que lib/api.ts usa.
 *
 * Tratamento de 429 (rate limit, spec §14.1): o fetch retorna 429 antes
 * de abrir o stream; devolvemos { rateLimited: true, retryAfter } para a
 * UI desabilitar o envio por N segundos.
 */

import { errorMessageFromBody } from "./api";
import type { Agent } from "./types";

export type ChatEventType =
  | "text"
  | "config_update"
  | "validation_error"
  | "done";

export interface ChatEvent {
  type: ChatEventType;
  data: unknown;
}

export interface ChatCallbacks {
  /** Texto da resposta do assistente (evento "text"). */
  onText?: (text: string) => void;
  /** Configuração atualizada do draft (evento "config_update"). */
  onConfigUpdate?: (config: Partial<Agent>) => void;
  /** Erros de validação do contrato (evento "validation_error"). */
  onValidationError?: (errors: unknown) => void;
  /** Fim do stream (evento "done"). Devolve o draftId. */
  onDone?: (draftId: string) => void;
  /** Erro de rede/parse (não 429). */
  onError?: (error: Error) => void;
}

export interface ChatResult {
  /** true se a requisição foi bloqueada por rate limit (429). */
  rateLimited: boolean;
  /** Segundos para reabilitar o envio (apenas se rateLimited). */
  retryAfter?: number;
  /** draftId retornado no evento "done" (quando o stream terminou). */
  draftId?: string;
}

/**
 * Obtém o token de sessão (mesmo endpoint de lib/api.ts).
 * Cache em memória; não usa localStorage.
 */
let cachedToken: string | null = null;

/**
 * Limpa o token cacheado. Exposto apenas para testes (evita estado
 * compartilhado entre casos).
 */
export function __resetAgentChatTokenForTests(): void {
  cachedToken = null;
}

async function getToken(): Promise<string> {
  if (cachedToken) return cachedToken;
  const res = await fetch("/api/session-token", {
    method: "GET",
    credentials: "same-origin",
  });
  if (!res.ok) {
    throw new Error("unauthorized");
  }
  const data = (await res.json()) as { accessToken: string };
  cachedToken = data.accessToken;
  return cachedToken;
}

/**
 * Envia uma mensagem ao chat de construção e consome o stream SSE.
 *
 * @param path  "/api/agents/chat" (novo) ou "/api/agents/{id}/chat" (edição).
 * @param message Texto da mensagem do usuário.
 * @param draftId draftId da sessão (opcional; continua a conversa).
 * @param callbacks Callbacks de eventos.
 * @param signal AbortSignal para cancelar o stream.
 */
export async function sendAgentChat(
  path: string,
  message: string,
  draftId: string | null,
  callbacks: ChatCallbacks = {},
  signal?: AbortSignal
): Promise<ChatResult> {
  const token = await getToken();

  const res = await fetch(path, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ message, draftId: draftId ?? undefined }),
    credentials: "same-origin",
    signal,
  });

  // 429: rate limit (spec §14.1). O body segue o envelope de erro.
  if (res.status === 429) {
    let retryAfter: number | undefined;
    try {
      const body = (await res.json()) as {
        details?: { retryAfter?: number };
      };
      retryAfter = body.details?.retryAfter;
    } catch {
      // sem body: usa retryAfter padrão conservador.
      retryAfter = 30;
    }
    return { rateLimited: true, retryAfter };
  }

  if (!res.ok) {
    let errorBody: unknown = {};
    try {
      errorBody = await res.json();
    } catch {
      // ignora
    }
    const err = new Error(errorMessageFromBody(res.status, errorBody));
    callbacks.onError?.(err);
    return { rateLimited: false };
  }

  if (!res.body) {
    const err = new Error("stream body indisponível");
    callbacks.onError?.(err);
    return { rateLimited: false };
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let draftIdOut: string | undefined;

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE: eventos separados por linha em branco.
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";

      for (const part of parts) {
        const event = parseSseChunk(part);
        if (!event) continue;
        dispatchEvent(event, callbacks);
        if (event.type === "done") {
          const data = event.data as { draftId?: string };
          draftIdOut = data?.draftId;
        }
      }
    }
  } catch (e) {
    // AbortError: o usuário cancelou o stream. Não é erro.
    if (e instanceof DOMException && e.name === "AbortError") {
      return { rateLimited: false, draftId: draftIdOut };
    }
    const err = e instanceof Error ? e : new Error(String(e));
    callbacks.onError?.(err);
    return { rateLimited: false, draftId: draftIdOut };
  }

  return { rateLimited: false, draftId: draftIdOut };
}

/**
 * Restaura um rascunho a partir da config da tela (POST /api/agents/chat/restore).
 * Usado quando o draft expirou no servidor (404 draft_not_found no confirm):
 * recria o rascunho com o que ainda está visível e devolve o novo draftId.
 */
export async function restoreAgentDraft(
  config: Record<string, unknown>,
  messages?: Array<{ role: string; content: string }>
): Promise<{ draftId: string }> {
  const token = await getToken();
  const res = await fetch("/api/agents/chat/restore", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ config, messages }),
    credentials: "same-origin",
  });

  if (!res.ok) {
    let errorBody: unknown = {};
    try {
      errorBody = await res.json();
    } catch {
      // ignora
    }
    throw new Error(errorMessageFromBody(res.status, errorBody));
  }

  return (await res.json()) as { draftId: string };
}

/**
 * Confirma o draft e salva o agente (POST /api/agents/chat/confirm).
 * Retorna o agente criado (id, name, ...).
 */
export async function confirmAgentDraft(draftId: string): Promise<Agent> {
  const token = await getToken();
  const res = await fetch("/api/agents/chat/confirm", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ draftId }),
    credentials: "same-origin",
  });

  if (!res.ok) {
    let errorBody: unknown = {};
    try {
      errorBody = await res.json();
    } catch {
      // ignora
    }
    // E1: mensagem pt-BR do envelope (ex.: agent_name_exists), não o "conflict" cru.
    const err = new Error(errorMessageFromBody(res.status, errorBody)) as Error & {
      status?: number;
      code?: string;
    };
    // Task 3: expõe status + code do envelope no erro para a UI decidir a
    // recuperação (ex.: 404 + code "draft_not_found" → rascunho expirou).
    err.status = res.status;
    const body = errorBody as { code?: unknown } | null;
    if (body && typeof body.code === "string") err.code = body.code;
    throw err;
  }

  return (await res.json()) as Agent;
}

/**
 * Parseia um chunk SSE (uma linha "data: {...}").
 */
function parseSseChunk(chunk: string): ChatEvent | null {
  const lines = chunk.split("\n");
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("data:")) continue;
    const payload = trimmed.slice(5).trim();
    if (!payload) continue;
    try {
      const parsed = JSON.parse(payload) as ChatEvent;
      if (parsed && typeof parsed.type === "string") {
        return parsed;
      }
    } catch {
      // linha inválida: ignora.
    }
  }
  return null;
}

function dispatchEvent(event: ChatEvent, callbacks: ChatCallbacks): void {
  switch (event.type) {
    case "text":
      callbacks.onText?.(event.data as string);
      break;
    case "config_update":
      callbacks.onConfigUpdate?.(event.data as Partial<Agent>);
      break;
    case "validation_error":
      callbacks.onValidationError?.(event.data);
      break;
    case "done":
      callbacks.onDone?.((event.data as { draftId?: string })?.draftId ?? "");
      break;
    default:
      break;
  }
}
