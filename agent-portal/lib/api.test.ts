import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { api, ApiError, invalidateToken } from "./api";

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
      expect(apiErr.message).toBe("not_found");
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
    const mockLocation = { href: "" };
    Object.defineProperty(window, "location", {
      value: mockLocation,
      writable: true,
      configurable: true,
    });

    mockFetch
      .mockResolvedValueOnce(mockResponse(200, { accessToken: "test-token" }))
      .mockResolvedValueOnce(
        mockResponse(401, { error: "unauthorized", code: "not_authenticated" })
      );

    await expect(api.get("/api/agents")).rejects.toThrow(ApiError);
    expect(mockLocation.href).toBe("/login");

    Object.defineProperty(window, "location", {
      value: originalLocation,
      writable: true,
      configurable: true,
    });
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
