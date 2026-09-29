import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { api, ApiError, errorMessageFromBody, invalidateToken } from "./api";

const mockFetch = vi.fn();



function mockResponse(status: number, body?: unknown, headers?: Record<string, string>) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Error",
    json: async () => body,
    headers: new Headers(headers),
  };
}

beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch);
  vi.clearAllMocks();
  invalidateToken();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api", () => {
  it("gets token from /api/session-token and injects Authorization header", async () => {
    mockFetch
      .mockResolvedValueOnce(mockResponse(200, { accessToken: "test-token" }))
      .mockResolvedValueOnce(mockResponse(200, { id: "1", name: "Agent" }));

    const result = await api.get("/api/agents/1");

    expect(mockFetch).toHaveBeenCalledTimes(2);
    const firstCall = mockFetch.mock.calls[0][0] as string;
    expect(firstCall).toContain("/api/session-token");

    const secondCall = mockFetch.mock.calls[1];
    const secondUrl = secondCall[0] as string;
    const secondOpts = secondCall[1] as RequestInit;
    expect(secondUrl).toContain("/api/agents/1");
    expect((secondOpts.headers as Record<string, string>).Authorization).toBe(
      "Bearer test-token"
    );

    expect(result).toEqual({ id: "1", name: "Agent" });
  });

  it("caches the token (does not re-fetch on second call)", async () => {
    mockFetch
      .mockResolvedValueOnce(mockResponse(200, { accessToken: "test-token" }))
      .mockResolvedValueOnce(mockResponse(200, { id: "1" }))
      .mockResolvedValueOnce(mockResponse(200, { id: "2" }));

    await api.get("/api/agents/1");
    await api.get("/api/agents/2");

    // Only 3 fetches: 1 for token + 2 for data
    expect(mockFetch).toHaveBeenCalledTimes(3);
  });

  it("throws ApiError with envelope on 4xx", async () => {
    mockFetch
      .mockResolvedValueOnce(mockResponse(200, { accessToken: "test-token" }))
      .mockResolvedValueOnce(
        mockResponse(404, { error: "not_found", code: "agent_not_found" })
      )
      .mockResolvedValueOnce(
        mockResponse(404, { error: "not_found", code: "agent_not_found" })
      );

    await expect(api.get("/api/agents/999")).rejects.toThrow(ApiError);
    try {
      await api.get("/api/agents/999");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      const apiErr = e as ApiError;
      expect(apiErr.status).toBe(404);
      expect(apiErr.code).toBe("agent_not_found");
      expect(apiErr.message).toBe("Recurso não encontrado.");
    }
  });

  it("throws ApiError with details on 400 validation error", async () => {
    mockFetch
      .mockResolvedValueOnce(mockResponse(200, { accessToken: "test-token" }))
      .mockResolvedValueOnce(
        mockResponse(400, {
          error: "validation error",
          code: "invalid_graph",
          details: { errors: [{ rule: 1, message: "missing entry" }] },
        })
      );

    try {
      await api.put("/api/pipelines/1", { nodes: [] });
    } catch (e) {
      const apiErr = e as ApiError;
      expect(apiErr.status).toBe(400);
      expect(apiErr.code).toBe("invalid_graph");
      expect(apiErr.details?.errors).toEqual([{ rule: 1, message: "missing entry" }]);
    }
  });

  it("popula method, path e describe() no ApiError", async () => {
    mockFetch
      .mockResolvedValueOnce(mockResponse(200, { accessToken: "test-token" }))
      .mockResolvedValueOnce(mockResponse(404, { error: "not_found", code: "not_found" }));

    try {
      await api.post("/api/agents/chat/confirm", {});
      throw new Error("deveria ter lançado");
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
      const apiErr = e as ApiError;
      expect(apiErr.method).toBe("POST");
      expect(apiErr.path).toBe("/api/agents/chat/confirm");
      expect(apiErr.describe()).toContain("HTTP 404 · POST /api/agents/chat/confirm");
    }
  });

  it("extracts retryAfter from 429 response", async () => {
    mockFetch
      .mockResolvedValueOnce(mockResponse(200, { accessToken: "test-token" }))
      .mockResolvedValueOnce(
        mockResponse(429, {
          error: "rate_limited",
          code: "rate_limited",
          details: { retryAfter: 30 },
        })
      );

    try {
      await api.post("/api/pipelines/1/execute", {});
    } catch (e) {
      const apiErr = e as ApiError;
      expect(apiErr.status).toBe(429);
      expect(apiErr.retryAfter).toBe(30);
    }
  });

  it("redirects to /login on 401", async () => {
    const originalLocation = window.location;
    const mockLocation = { href: "", pathname: "/agents" };
    Object.defineProperty(window, "location", {
      value: mockLocation,
      writable: true,
      configurable: true,
    });

    // 401 mesmo depois de buscar um token novo: sessão morta.
    mockFetch
      .mockResolvedValueOnce(mockResponse(200, { accessToken: "test-token" }))
      .mockResolvedValueOnce(mockResponse(401, { error: "unauthorized", code: "not_authenticated" }))
      .mockResolvedValueOnce(mockResponse(200, { accessToken: "test-token-2" }))
      .mockResolvedValueOnce(mockResponse(401, { error: "unauthorized", code: "not_authenticated" }));

    await expect(api.get("/api/agents")).rejects.toThrow(ApiError);
    expect(mockLocation.href).toBe("/login?error=session_expired");

    Object.defineProperty(window, "location", {
      value: originalLocation,
      writable: true,
      configurable: true,
    });
  });

  it("retries once with a fresh session token after an expired access token", async () => {
    mockFetch
      .mockResolvedValueOnce(mockResponse(200, { accessToken: "expired" }))
      .mockResolvedValueOnce(mockResponse(401, { error: "unauthorized", code: "not_authenticated" }))
      .mockResolvedValueOnce(mockResponse(200, { accessToken: "renewed" }))
      .mockResolvedValueOnce(mockResponse(200, { items: [], total: 0, page: 1, limit: 20 }));

    const res = await api.get<{ items: unknown[] }>("/api/agents");
    expect(res.items).toEqual([]);
    const lastCall = mockFetch.mock.calls[3];
    expect(lastCall[1].headers.Authorization).toBe("Bearer renewed");
  });

  it("returns undefined for 204 No Content", async () => {
    mockFetch
      .mockResolvedValueOnce(mockResponse(200, { accessToken: "test-token" }))
      .mockResolvedValueOnce({
        ok: true,
        status: 204,
        statusText: "No Content",
        json: async () => {
          throw new Error("No body");
        },
      });

    const result = await api.delete("/api/agents/1");
    expect(result).toBeUndefined();
  });

  it("sends query parameters", async () => {
    mockFetch
      .mockResolvedValueOnce(mockResponse(200, { accessToken: "test-token" }))
      .mockResolvedValueOnce(
        mockResponse(200, { items: [], total: 0, page: 1, limit: 20 })
      );

    await api.list("/api/agents", { page: 2, limit: 10 });

    const secondCall = mockFetch.mock.calls[1];
    const url = secondCall[0] as string;
    expect(url).toContain("page=2");
    expect(url).toContain("limit=10");
  });

  it("sends JSON body for POST", async () => {
    mockFetch
      .mockResolvedValueOnce(mockResponse(200, { accessToken: "test-token" }))
      .mockResolvedValueOnce(mockResponse(201, { id: "new" }));

    await api.post("/api/agents", { name: "Test" });

    const secondCall = mockFetch.mock.calls[1];
    const opts = secondCall[1] as RequestInit;
    expect(opts.method).toBe("POST");
    expect(opts.body).toBe(JSON.stringify({ name: "Test" }));
    expect((opts.headers as Record<string, string>)["Content-Type"]).toBe(
      "application/json"
    );
  });

  it("sends FormData body without Content-Type header", async () => {
    mockFetch
      .mockResolvedValueOnce(mockResponse(200, { accessToken: "test-token" }))
      .mockResolvedValueOnce(mockResponse(201, { id: "doc" }));

    const formData = new FormData();
    formData.append("file", "test");

    await api.post("/api/knowledge/1/upload", formData);

    const secondCall = mockFetch.mock.calls[1];
    const opts = secondCall[1] as RequestInit;
    expect(opts.body).toBe(formData);
    expect((opts.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
  });
});

describe("errorMessageFromBody (E1)", () => {
  it("maps specific codes to pt-BR text instead of the raw envelope", () => {
    expect(errorMessageFromBody(409, { error: "conflict", code: "email_already_exists" })).toBe(
      "Já existe uma conta com este e-mail."
    );
    expect(errorMessageFromBody(409, { error: "conflict", code: "agent_name_exists" })).toBe(
      "Já existe um agente com este nome."
    );
  });

  it("falls back to the generic error class with the first validation detail", () => {
    expect(
      errorMessageFromBody(422, {
        error: "unprocessable",
        code: "schema_validation",
        details: { errors: [{ loc: ["body", "outputs", 0, "type"], msg: "invalid port type" }] },
      })
    ).toBe("Dados inválidos. outputs.0.type: invalid port type");
  });

  it("appends the validation detail to a specific code message", () => {
    expect(
      errorMessageFromBody(422, {
        error: "validation failed",
        code: "tool_validation_failed",
        details: { errors: ["Script must define a function named 'execute'"] },
      })
    ).toBe("O código da tool não passou na validação. Script must define a function named 'execute'");
  });

  it("translates the new codes and surfaces details.message without repeating it", () => {
    expect(errorMessageFromBody(404, { error: "not_found", code: "run_not_found" })).toBe("Execução não encontrada.");
    expect(errorMessageFromBody(404, { error: "not_found", code: "document_not_found" })).toBe(
      "Documento não encontrado."
    );
    expect(errorMessageFromBody(404, { error: "not_found", code: "conversation_not_found" })).toBe(
      "Conversa não encontrada."
    );
    expect(
      errorMessageFromBody(400, {
        error: "validation error",
        code: "invalid_config",
        details: { message: "Config do Azure DevOps deve conter 'organization'." },
      })
    ).toBe("Configuração inválida. Config do Azure DevOps deve conter 'organization'.");
    // Mesmo texto no código e no details.message: aparece uma vez só.
    expect(
      errorMessageFromBody(413, {
        error: "payload too large",
        code: "archive_too_large",
        details: { message: "O workspace é grande demais para baixar como zip (limite de 200 MB)." },
      })
    ).toBe("O workspace é grande demais para baixar como zip (limite de 200 MB).");
    expect(errorMessageFromBody(400, { error: "x", code: "invalid_workspace" })).toMatch(/não existe mais/);
    expect(errorMessageFromBody(403, { error: "x", code: "mcp_capability_invalid" })).toMatch(/MCP/);
  });

  it("keeps FastAPI detail outside the envelope", () => {
    expect(errorMessageFromBody(404, { detail: "Not Found" })).toBe("Not Found");
  });
});

describe("api.download (zip do run)", () => {
  it("baixa com o bearer da sessão e devolve o blob e o nome do Content-Disposition", async () => {
    const blob = new Blob(["PK"], { type: "application/zip" });
    mockFetch
      .mockResolvedValueOnce(mockResponse(200, { accessToken: "test-token" }))
      .mockResolvedValueOnce({
        ...mockResponse(200, undefined, { "Content-Disposition": 'attachment; filename="meu-pipe-abc12345.zip"' }),
        blob: async () => blob,
      });

    const res = await api.download("/api/runs/r1/archive");

    const [url, opts] = mockFetch.mock.calls[1] as [string, RequestInit];
    expect(url).toBe("/api/runs/r1/archive");
    expect((opts.headers as Record<string, string>).Authorization).toBe("Bearer test-token");
    expect(res.blob).toBe(blob);
    expect(res.filename).toBe("meu-pipe-abc12345.zip");
  });

  it("erro vira ApiError com a mensagem do código", async () => {
    mockFetch
      .mockResolvedValueOnce(mockResponse(200, { accessToken: "test-token" }))
      .mockResolvedValueOnce(mockResponse(404, { error: "not_found", code: "workspace_not_found" }));

    await expect(api.download("/api/runs/r1/archive")).rejects.toMatchObject({
      status: 404,
      message: expect.stringMatching(/arquivos desta execução não estão mais disponíveis/i),
    });
  });
});
