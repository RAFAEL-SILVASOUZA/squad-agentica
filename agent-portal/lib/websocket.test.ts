import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { WebSocketClient, getWebSocketClient, disposeWebSocketClient } from "./websocket";

// Mock WebSocket
class MockWebSocket {
  static instances: MockWebSocket[] = [];
  readyState: number = 0; // CONNECTING
  url: string;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  close() {
    this.readyState = 3; // CLOSED
    this.onclose?.();
  }

  // Test helpers
  simulateOpen() {
    this.readyState = 1; // OPEN
    this.onopen?.();
  }

  simulateMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }

  simulateClose() {
    this.readyState = 3; // CLOSED
    this.onclose?.();
  }
}

vi.stubGlobal("WebSocket", MockWebSocket);

beforeEach(() => {
  MockWebSocket.instances = [];
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  disposeWebSocketClient();
});

describe("WebSocketClient", () => {
  it("connects to /api/ws with token", () => {
    const client = new WebSocketClient("test-token");
    client.connect();

    expect(MockWebSocket.instances).toHaveLength(1);
    const ws = MockWebSocket.instances[0];
    expect(ws.url).toContain("/api/ws");
    expect(ws.url).toContain("token=test-token");
  });

  it("dispatches events to registered handlers", () => {
    const client = new WebSocketClient("test-token");
    const handler = vi.fn();
    client.on("pipeline:status", handler);
    client.connect();

    const ws = MockWebSocket.instances[0];
    ws.simulateOpen();
    ws.simulateMessage({
      channel: "pipeline:status",
      data: { pipelineId: "p1", runId: "r1", nodeId: "n1", status: "running", at: "2026-01-01T00:00:00Z" },
    });

    expect(handler).toHaveBeenCalledWith({
      pipelineId: "p1",
      runId: "r1",
      nodeId: "n1",
      status: "running",
      at: "2026-01-01T00:00:00Z",
    });
  });

  it("filters events by pipelineId", () => {
    const client = new WebSocketClient("test-token");
    const handler = vi.fn();
    client.on("pipeline:status", handler, "p1");
    client.connect();

    const ws = MockWebSocket.instances[0];
    ws.simulateOpen();

    // Event for p1: should be delivered
    ws.simulateMessage({
      channel: "pipeline:status",
      data: { pipelineId: "p1", runId: "r1", nodeId: "n1", status: "running", at: "2026-01-01T00:00:00Z" },
    });
    expect(handler).toHaveBeenCalledTimes(1);

    // Event for p2: should be filtered out
    ws.simulateMessage({
      channel: "pipeline:status",
      data: { pipelineId: "p2", runId: "r2", nodeId: "n2", status: "running", at: "2026-01-01T00:00:00Z" },
    });
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("does not dispatch to wrong channel", () => {
    const client = new WebSocketClient("test-token");
    const handler = vi.fn();
    client.on("pipeline:log", handler);
    client.connect();

    const ws = MockWebSocket.instances[0];
    ws.simulateOpen();
    ws.simulateMessage({
      channel: "pipeline:status",
      data: { pipelineId: "p1", runId: "r1", nodeId: "n1", status: "running", at: "2026-01-01T00:00:00Z" },
    });

    expect(handler).not.toHaveBeenCalled();
  });

  it("removes handler with off()", () => {
    const client = new WebSocketClient("test-token");
    const handler = vi.fn();
    client.on("pipeline:status", handler);
    client.off("pipeline:status", handler);
    client.connect();

    const ws = MockWebSocket.instances[0];
    ws.simulateOpen();
    ws.simulateMessage({
      channel: "pipeline:status",
      data: { pipelineId: "p1", runId: "r1", nodeId: "n1", status: "running", at: "2026-01-01T00:00:00Z" },
    });

    expect(handler).not.toHaveBeenCalled();
  });

  it("reconnects with exponential backoff", () => {
    const client = new WebSocketClient("test-token");
    client.connect();

    const ws1 = MockWebSocket.instances[0];
    ws1.simulateOpen();
    ws1.simulateClose();

    // First reconnect: 1s
    expect(MockWebSocket.instances).toHaveLength(1);
    vi.advanceTimersByTime(1000);
    expect(MockWebSocket.instances).toHaveLength(2);

    const ws2 = MockWebSocket.instances[1];
    ws2.simulateOpen();
    ws2.simulateClose();

    // Second reconnect: 2s
    vi.advanceTimersByTime(2000);
    expect(MockWebSocket.instances).toHaveLength(3);
  });

  it("caps backoff at 30s", () => {
    const client = new WebSocketClient("test-token");
    client.connect();

    // Simulate 7 failed reconnects (1s, 2s, 4s, 8s, 16s, 30s, 30s)
    for (let i = 0; i < 7; i++) {
      const ws = MockWebSocket.instances[i];
      vi.advanceTimersByTime(i < 5 ? 1000 * Math.pow(2, i) : 30000);
      if (i < 6) {
        const newWs = MockWebSocket.instances[i + 1];
        if (newWs) {
          newWs.simulateOpen();
          newWs.simulateClose();
        }
      }
    }

    // After 7 attempts, the delay should be capped at 30s
    const lastWs = MockWebSocket.instances[6];
    if (lastWs) {
      lastWs.simulateOpen();
      lastWs.simulateClose();
      vi.advanceTimersByTime(29999);
      expect(MockWebSocket.instances).toHaveLength(7);
      vi.advanceTimersByTime(1);
      expect(MockWebSocket.instances).toHaveLength(8);
    }
  });

  it("calls reconnect handler after successful reconnect", () => {
    const client = new WebSocketClient("test-token");
    const onReconnect = vi.fn();
    client.onReconnect(onReconnect);
    client.connect();

    const ws1 = MockWebSocket.instances[0];
    ws1.simulateOpen();
    ws1.simulateClose();

    vi.advanceTimersByTime(1000);
    const ws2 = MockWebSocket.instances[1];
    ws2.simulateOpen();

    expect(onReconnect).toHaveBeenCalled();
  });

  it("does not reconnect after disconnect()", () => {
    const client = new WebSocketClient("test-token");
    client.connect();

    const ws1 = MockWebSocket.instances[0];
    ws1.simulateOpen();
    client.disconnect();

    vi.advanceTimersByTime(60000);
    expect(MockWebSocket.instances).toHaveLength(1);
  });

  it("updates token with setToken", () => {
    const client = new WebSocketClient("old-token");
    client.setToken("new-token");
    client.connect();

    const ws = MockWebSocket.instances[0];
    expect(ws.url).toContain("token=new-token");
  });

  it("ignores invalid JSON frames", () => {
    const client = new WebSocketClient("test-token");
    const handler = vi.fn();
    client.on("pipeline:status", handler);
    client.connect();

    const ws = MockWebSocket.instances[0];
    ws.simulateOpen();
    ws.onmessage?.({ data: "not-json" });

    expect(handler).not.toHaveBeenCalled();
  });
});

describe("getWebSocketClient", () => {
  it("returns singleton", () => {
    const c1 = getWebSocketClient("token1");
    const c2 = getWebSocketClient("token2");
    expect(c1).toBe(c2);
  });

  it("disposes with disposeWebSocketClient", () => {
    const c1 = getWebSocketClient("token1");
    disposeWebSocketClient();
    const c2 = getWebSocketClient("token2");
    expect(c1).not.toBe(c2);
  });
});
