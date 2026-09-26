/**
 * Cliente de API (contrato §5, §8).
 * - Token obtido via GET /api/session-token (cache em memória, não localStorage).
 * - Envelope de erro tipado: { error, code, details }.
 * - 401 → redireciona para /login.
 * - 429 → expõe retryAfter.
 * - Paginação: { items, total, page, limit }.
 */

import type { ApiErrorBody, PaginatedResponse } from "./types";

export class ApiError extends Error {
  status: number;
  code: string;
  details?: Record<string, unknown>;
  retryAfter?: number;

  constructor(status: number, body: ApiErrorBody) {
    super(body.error);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
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
