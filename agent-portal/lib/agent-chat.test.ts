import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { sendAgentChat, confirmAgentDraft, __resetAgentChatTokenForTests } from "./agent-chat";

function mockTokenFetch() {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ accessToken: "test-token" }),
  });
}

function sseStream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

function mockChatFetch(chunks: string[]) {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    body: sseStream(chunks),
  });
}

beforeEach(() => {
  __resetAgentChatTokenForTests();
  // Primeiro fetch = token, depois = chat.
  const tokenFetch = mockTokenFetch();
  vi.stubGlobal("fetch", tokenFetch);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("sendAgentChat", () => {
  it("dispatches text, config_update and done events", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ accessToken: "test-token" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        body: sseStream([
          'data: {"type":"text","data":"Olá"}\n\n',
          'data: {"type":"config_update","data":{"name":"Dev"}}\n\n',
          'data: {"type":"done","data":{"draftId":"d-1"}}\n\n',
        ]),
      });
    vi.stubGlobal("fetch", fetchMock);

    const onText = vi.fn();
    const onConfigUpdate = vi.fn();
    const onDone = vi.fn();

    const result = await sendAgentChat(
      "/api/agents/chat",
      "crie um agente",
      null,
      { onText, onConfigUpdate, onDone }
    );

    expect(onText).toHaveBeenCalledWith("Olá");
    expect(onConfigUpdate).toHaveBeenCalledWith({ name: "Dev" });
    expect(onDone).toHaveBeenCalledWith("d-1");
    expect(result.rateLimited).toBe(false);
    expect(result.draftId).toBe("d-1");
  });

  it("sends draftId in the body when provided", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ accessToken: "test-token" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        body: sseStream(['data: {"type":"done","data":{"draftId":"d-9"}}\n\n']),
      });
    vi.stubGlobal("fetch", fetchMock);

    await sendAgentChat("/api/agents/a1/chat", "ajuste", "d-9", {});

    const chatCall = fetchMock.mock.calls[1];
    const body = JSON.parse(chatCall[1].body as string);
    expect(body).toEqual({ message: "ajuste", draftId: "d-9" });
  });

  it("returns rateLimited with retryAfter on 429", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ accessToken: "test-token" }),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 429,
        json: async () => ({
          error: "rate_limited",
          code: "rate_limited",
          details: { retryAfter: 42 },
        }),
      });
    vi.stubGlobal("fetch", fetchMock);

    const result = await sendAgentChat("/api/agents/chat", "oi", null, {});

    expect(result.rateLimited).toBe(true);
    expect(result.retryAfter).toBe(42);
  });

  it("calls onError on non-2xx non-429", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ accessToken: "test-token" }),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ error: "draft_not_found", code: "not_found" }),
      });
    vi.stubGlobal("fetch", fetchMock);

    const onError = vi.fn();
    const result = await sendAgentChat(
      "/api/agents/chat",
      "oi",
      "bad",
      { onError }
    );

    expect(onError).toHaveBeenCalled();
    expect(result.rateLimited).toBe(false);
  });

  it("handles abort without calling onError", async () => {
    const controller = new AbortController();
    // Stream cujo reader.read() rejeita com AbortError quando abortado.
    const abortingStream = new ReadableStream<Uint8Array>({
      pull() {
        return new Promise((_, reject) => {
          if (controller.signal.aborted) {
            reject(new DOMException("Aborted", "AbortError"));
            return;
          }
          controller.signal.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        });
      },
    });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ accessToken: "test-token" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        body: abortingStream,
      });
    vi.stubGlobal("fetch", fetchMock);

    // Aborta logo após iniciar o stream.
    setTimeout(() => controller.abort(), 10);

    const onError = vi.fn();
    const result = await sendAgentChat(
      "/api/agents/chat",
      "oi",
      null,
      { onError },
      controller.signal
    );

    expect(onError).not.toHaveBeenCalled();
    expect(result.rateLimited).toBe(false);
  });
});

describe("confirmAgentDraft", () => {
  it("posts draftId and returns the created agent", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ accessToken: "test-token" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => ({ id: "agent-1", name: "Dev", type: "custom" }),
      });
    vi.stubGlobal("fetch", fetchMock);

    const agent = await confirmAgentDraft("d-1");

    expect(agent.id).toBe("agent-1");
    const call = fetchMock.mock.calls[1];
    expect(call[0]).toBe("/api/agents/chat/confirm");
    expect(JSON.parse(call[1].body as string)).toEqual({ draftId: "d-1" });
  });

  it("throws on 404 draft_not_found", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ accessToken: "test-token" }),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ error: "not_found", code: "draft_not_found" }),
      });
    vi.stubGlobal("fetch", fetchMock);

    await expect(confirmAgentDraft("missing")).rejects.toThrow();
  });
});
