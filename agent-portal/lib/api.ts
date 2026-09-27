/**
 * Cliente de API (contrato §5, §8).
 * - Token obtido via GET /api/session-token (cache em memória, não localStorage).
 * - Envelope de erro tipado: { error, code, details }.
 * - 401 → redireciona para /login.
 * - 429 → expõe retryAfter.
 * - Paginação: { items, total, page, limit }.
 */

import type { ApiErrorBody, PaginatedResponse } from "./types";

// E1: o envelope do contrato (§8) traz `error`/`code` legíveis por máquina
// ("conflict", "validation error"); a UI mostrava esse texto cru. A mensagem
// exibida vem do `code` (específico) ou do `error` (genérico), em pt-BR.
const CODE_MESSAGES: Record<string, string> = {
  email_already_exists: "Já existe uma conta com este e-mail.",
  invalid_credentials: "E-mail ou senha inválidos.",
  not_authenticated: "Sessão expirada. Entre novamente.",
  agent_name_exists: "Já existe um agente com este nome.",
  skill_name_exists: "Já existe uma skill com este nome.",
  tool_name_exists: "Já existe uma tool com este nome.",
  mcp_server_name_exists: "Já existe um servidor MCP com este nome.",
  knowledge_base_name_exists: "Já existe uma base de conhecimento com este nome.",
  incomplete_draft: "O rascunho do agente ainda não tem nome. Continue a conversa antes de salvar.",
  pipeline_already_running: "Este pipeline já está em execução.",
  graph_running: "O pipeline está em execução; aguarde ou pare o run antes de editar.",
  already_responded: "Esta aprovação já foi respondida.",
  no_active_run: "Não há execução ativa para este pipeline.",
  no_paused_run: "Não há execução pausada para retomar.",
  invalid_graph: "O pipeline tem erros de validação.",
  mcp_config_invalid: "Configuração do servidor MCP inválida.",
  tool_validation_failed: "O código da tool não passou na validação.",
  invalid_file_type: "Tipo de arquivo não suportado.",
  file_too_large: "Arquivo grande demais.",
  ingest_error: "Falha ao processar o documento.",
  storage_error: "Falha no armazenamento de arquivos. Tente novamente.",
  github_error: "Falha ao consultar o GitHub.",
  rate_limited: "Muitas requisições. Aguarde um instante e tente de novo.",
  internal_error: "Erro interno do servidor. Tente novamente.",
};

const ERROR_MESSAGES: Record<string, string> = {
  conflict: "Conflito com o estado atual do recurso.",
  "validation error": "Dados inválidos.",
  unprocessable: "Dados inválidos.",
  not_found: "Recurso não encontrado.",
  "not found": "Recurso não encontrado.",
  forbidden: "Acesso negado.",
  unauthorized: "Sessão expirada. Entre novamente.",
  rate_limited: "Muitas requisições. Aguarde um instante e tente de novo.",
  "internal error": "Erro interno do servidor. Tente novamente.",
};

function validationSummary(details: unknown): string | null {
  const errors = (details as { errors?: unknown } | undefined)?.errors;
  if (!Array.isArray(errors) || errors.length === 0) return null;
  const first = errors[0] as Record<string, unknown> | string;
  if (typeof first === "string") return first;
  const loc = Array.isArray(first.loc) ? first.loc.filter((p) => p !== "body").join(".") : "";
  const msg = typeof first.message === "string" ? first.message : typeof first.msg === "string" ? first.msg : "";
  if (!msg) return null;
  return loc ? `${loc}: ${msg}` : msg;
}

function extractErrorMessage(
  status: number,
  body: { error?: unknown; detail?: unknown; code?: string; details?: unknown }
): { message: string; code: string } {
  const code = body.code ?? "";
  if (CODE_MESSAGES[code]) {
    // O detalhe (ex.: erro de validação do script) diz ao usuário o que corrigir.
    const summary = validationSummary(body.details);
    return { message: summary ? `${CODE_MESSAGES[code]} ${summary}` : CODE_MESSAGES[code], code };
  }
  if (typeof body.error === "string" && ERROR_MESSAGES[body.error.trim()]) {
    const base = ERROR_MESSAGES[body.error.trim()];
    const summary = validationSummary(body.details);
    return { message: summary ? `${base} ${summary}` : base, code };
  }
  // Fora do envelope (ex.: 404 do FastAPI com {"detail": "Not Found"}).
  const candidates = [body.error, body.detail];
  for (const c of candidates) {
    if (typeof c === "string" && c.trim()) {
      return { message: c.trim(), code };
    }
    if (c && typeof c === "object" && !Array.isArray(c)) {
      const o = c as Record<string, unknown>;
      if (typeof o.detail === "string" && o.detail.trim()) {
        return { message: o.detail.trim(), code };
      }
      if (typeof o.msg === "string" && o.msg.trim()) {
        return { message: o.msg.trim(), code };
      }
    }
  }
  return { message: `Falha na requisição (${status}).`, code };
}

/** Mensagem legível (pt-BR) para um corpo de erro da API. */
export function errorMessageFromBody(status: number, body: unknown): string {
  const obj = body && typeof body === "object" ? (body as Record<string, never>) : {};
  return extractErrorMessage(status, obj).message;
}

export class ApiError extends Error {
  status: number;
  code: string;
  details?: Record<string, unknown>;
  retryAfter?: number;

  constructor(status: number, body: ApiErrorBody) {
    const { message, code } = extractErrorMessage(status, body as never);
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = body.details;

    if (status === 429 && body.details?.retryAfter !== undefined) {
      this.retryAfter = Number(body.details.retryAfter);
    }
  }
}

let cachedToken: string | null = null;
let tokenPromise: Promise<string> | null = null;

/**
 * Obtém o token de sessão via GET /api/session-token.
 * Cache em memória (não localStorage).
 */
async function getToken(): Promise<string> {
  if (cachedToken) return cachedToken;

  if (tokenPromise) return tokenPromise;

  tokenPromise = (async () => {
    const res = await fetch("/api/session-token", {
      method: "GET",
      credentials: "same-origin",
    });

    if (!res.ok) {
      cachedToken = null;
      tokenPromise = null;
      throw new ApiError(res.status, {
        error: "unauthorized",
        code: "not_authenticated",
      });
    }

    const data = (await res.json()) as { accessToken: string };
    cachedToken = data.accessToken;
    tokenPromise = null;
    return cachedToken;
  })();

  return tokenPromise;
}

/**
 * Invalida o token cacheado (usado em 401).
 */
export function invalidateToken(): void {
  cachedToken = null;
  tokenPromise = null;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined>;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, headers: extraHeaders, signal } = opts;

  const token = await getToken();

  let url: string;
  if (query) {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined) {
        params.set(key, String(value));
      }
    }
    const qs = params.toString();
    url = qs ? `${path}${path.includes("?") ? "&" : "?"}${qs}` : path;
  } else {
    url = path;
  }

  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    ...extraHeaders,
  };

  let requestBody: BodyInit | undefined;
  if (body !== undefined) {
    if (body instanceof FormData) {
      requestBody = body;
    } else {
      headers["Content-Type"] = "application/json";
      requestBody = JSON.stringify(body);
    }
  }

  const res = await fetch(url.toString(), {
    method,
    headers,
    body: requestBody,
    credentials: "same-origin",
    signal,
  });

  if (res.status === 401) {
    invalidateToken();
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
    throw new ApiError(401, { error: "unauthorized", code: "not_authenticated" });
  }

  if (!res.ok) {
    let errorBody: ApiErrorBody;
    try {
      errorBody = (await res.json()) as ApiErrorBody;
    } catch {
      errorBody = {
        error: res.statusText || "request failed",
        code: "unknown",
      };
    }
    throw new ApiError(res.status, errorBody);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return (await res.json()) as T;
}

export const api = {
  get<T>(path: string, opts?: Omit<RequestOptions, "method" | "body">): Promise<T> {
    return request<T>(path, { ...opts, method: "GET" });
  },

  post<T>(path: string, body?: unknown, opts?: Omit<RequestOptions, "method" | "body">): Promise<T> {
    return request<T>(path, { ...opts, method: "POST", body });
  },

  put<T>(path: string, body?: unknown, opts?: Omit<RequestOptions, "method" | "body">): Promise<T> {
    return request<T>(path, { ...opts, method: "PUT", body });
  },

  delete<T>(path: string, opts?: Omit<RequestOptions, "method" | "body">): Promise<T> {
    return request<T>(path, { ...opts, method: "DELETE" });
  },

  patch<T>(path: string, body?: unknown, opts?: Omit<RequestOptions, "method" | "body">): Promise<T> {
    return request<T>(path, { ...opts, method: "PATCH", body });
  },

  /**
   * Lista paginada (contrato §8).
   */
  list<T>(
    path: string,
    opts?: { page?: number; limit?: number; query?: Record<string, string | number | boolean | undefined> }
  ): Promise<PaginatedResponse<T>> {
    const query: Record<string, string | number | boolean | undefined> = {
      page: opts?.page,
      limit: opts?.limit,
      ...opts?.query,
    };
    return request<PaginatedResponse<T>>(path, { method: "GET", query });
  },
};
