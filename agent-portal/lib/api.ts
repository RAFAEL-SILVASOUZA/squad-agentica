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
  git_provider_error: "Falha ao acessar o provedor Git.",
  not_a_git_integration: "Esta conexão não é uma integração Git.",
  invalid_repository: "Repositório inválido. Confira a conexão e o nome informado.",
  secret_key_missing: "A chave de criptografia do servidor não está configurada. Contate o administrador.",
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
  duplicate_document: "Este arquivo já existe nesta base.",
  llm_error: "O modelo não conseguiu responder agora. Tente de novo.",
  storage_error: "Falha no armazenamento de arquivos. Tente novamente.",
  github_error: "Falha ao consultar o GitHub.",
  run_not_completed: "A execução ainda não terminou; publique depois que ela concluir.",
  workspace_not_found: "Os arquivos desta execução não estão mais disponíveis.",
  file_not_found: "Arquivo não encontrado nesta execução.",
  invalid_path: "Caminho de arquivo inválido.",
  rate_limited: "Muitas requisições. Aguarde um instante e tente de novo.",
  internal_error: "Erro interno do servidor. Tente novamente.",
  run_not_found: "Execução não encontrada.",
  document_not_found: "Documento não encontrado.",
  conversation_not_found: "Conversa não encontrada.",
  invalid_config: "Configuração inválida.",
  archive_too_large: "O workspace é grande demais para baixar como zip (limite de 200 MB).",
  invalid_workspace: "O workspace desta execução não existe mais (expirou ou foi removido).",
  diff_unavailable: "Não foi possível calcular as alterações do workspace agora. Tente de novo em instantes.",
  mcp_capability_invalid: "Chamada MCP recusada: credencial do run inválida.",
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
  if (!Array.isArray(errors) || errors.length === 0) {
    // `details.message` (pt-BR, vindo do servidor) também explica o erro.
    const message = (details as { message?: unknown } | undefined)?.message;
    return typeof message === "string" && message.trim() ? message.trim() : null;
  }
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
    const base = CODE_MESSAGES[code];
    return { message: summary && summary !== base ? `${base} ${summary}` : base, code };
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
      // Sessão sem token válido (refresh recusado): antes a tela ficava em
      // "Sessão expirada" com um "Tentar novamente" que nunca funcionava.
      if (res.status === 401) redirectToLogin();
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

function redirectToLogin(): void {
  if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    window.location.href = "/login?error=session_expired";
  }
}

/**
 * Envia a requisição autenticada e devolve a Response já validada (2xx);
 * 401 renova o token uma vez, demais erros viram ApiError.
 */
async function send(path: string, opts: RequestOptions = {}, retried = false): Promise<Response> {
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
    // O token em cache expira (15 min); a sessão NextAuth renova ao pedir um
    // token novo. Só vai para o login se, com o token novo, ainda for 401.
    invalidateToken();
    if (!retried) return send(path, opts, true);
    redirectToLogin();
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

  return res;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const res = await send(path, opts);

  if (res.status === 204) {
    return undefined as T;
  }

  return (await res.json()) as T;
}

/** Nome do arquivo em `Content-Disposition: attachment; filename="x.zip"`. */
function filenameFromDisposition(header: string | null): string | null {
  if (!header) return null;
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (utf8) {
    try {
      return decodeURIComponent(utf8[1].trim());
    } catch {
      // cai para o filename simples
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain ? plain[1].trim() : null;
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
   * Download binário autenticado (ex.: zip do run). Um `<a href>` comum não
   * manda o bearer da sessão; aqui o arquivo vem como Blob com o nome do
   * `Content-Disposition`.
   */
  async download(path: string): Promise<{ blob: Blob; filename: string | null }> {
    const res = await send(path, { method: "GET" });
    const filename = filenameFromDisposition(res.headers.get("Content-Disposition"));
    return { blob: await res.blob(), filename };
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
