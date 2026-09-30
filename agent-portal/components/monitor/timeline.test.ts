import { describe, it, expect } from "vitest";
import { buildTimeline } from "./timeline";

describe("buildTimeline", () => {
  it("computes duration from running to completed events", () => {
    const events = [
      { nodeId: "a", status: "running", at: "2026-01-01T10:00:00Z" },
      { nodeId: "a", status: "completed", at: "2026-01-01T10:00:12Z" },
    ];
    const result = buildTimeline(events, []);
    expect(result).toHaveLength(1);
    expect(result[0]).toEqual({
      nodeId: "a",
      startedAt: "2026-01-01T10:00:00Z",
      endedAt: "2026-01-01T10:00:12Z",
      durationMs: 12000,
      status: "completed",
    });
  });

  it("computes duration from running to failed events", () => {
    const events = [
      { nodeId: "b", status: "running", at: "2026-01-01T10:00:00Z" },
      { nodeId: "b", status: "failed", at: "2026-01-01T10:00:05Z" },
    ];
    const result = buildTimeline(events, []);
    expect(result[0]).toEqual({
      nodeId: "b",
      startedAt: "2026-01-01T10:00:00Z",
      endedAt: "2026-01-01T10:00:05Z",
      durationMs: 5000,
      status: "failed",
    });
  });

  it("node with only running event has no endedAt or durationMs", () => {
    const events = [{ nodeId: "c", status: "running", at: "2026-01-01T10:00:00Z" }];
    const result = buildTimeline(events, []);
    expect(result[0]).toEqual({
      nodeId: "c",
      startedAt: "2026-01-01T10:00:00Z",
      endedAt: undefined,
      durationMs: undefined,
      status: "running",
    });
  });

  it("falls back to checkpoints when no events exist", () => {
    const checkpoints = [
      { nodeId: "d", timestamp: "2026-01-01T10:05:00Z", status: "completed" },
    ];
    const result = buildTimeline([], checkpoints);
    expect(result).toHaveLength(1);
    expect(result[0]).toEqual({
      nodeId: "d",
      startedAt: undefined,
      endedAt: "2026-01-01T10:05:00Z",
      durationMs: undefined,
      status: "completed",
    });
  });

  it("events take priority over checkpoints for the same node", () => {
    const events = [
      { nodeId: "e", status: "running", at: "2026-01-01T10:00:00Z" },
      { nodeId: "e", status: "completed", at: "2026-01-01T10:00:10Z" },
    ];
    const checkpoints = [
      { nodeId: "e", timestamp: "2026-01-01T10:05:00Z", status: "completed" },
    ];
    const result = buildTimeline(events, checkpoints);
    expect(result).toHaveLength(1);
    expect(result[0].startedAt).toBe("2026-01-01T10:00:00Z");
    expect(result[0].durationMs).toBe(10000);
  });

  it("handles multiple nodes independently", () => {
    const events = [
      { nodeId: "a", status: "running", at: "2026-01-01T10:00:00Z" },
      { nodeId: "b", status: "running", at: "2026-01-01T10:00:05Z" },
      { nodeId: "a", status: "completed", at: "2026-01-01T10:00:10Z" },
      { nodeId: "b", status: "failed", at: "2026-01-01T10:00:15Z" },
    ];
    const result = buildTimeline(events, []);
    expect(result).toHaveLength(2);
    expect(result.find((r) => r.nodeId === "a")?.durationMs).toBe(10000);
    expect(result.find((r) => r.nodeId === "b")?.durationMs).toBe(10000);
  });

  it("ignores completed/failed before running for the same node", () => {
    // Um completed antes do running não conta como fim.
    const events = [
      { nodeId: "a", status: "completed", at: "2026-01-01T09:00:00Z" },
      { nodeId: "a", status: "running", at: "2026-01-01T10:00:00Z" },
      { nodeId: "a", status: "completed", at: "2026-01-01T10:00:03Z" },
    ];
    const result = buildTimeline(events, []);
    expect(result[0].startedAt).toBe("2026-01-01T10:00:00Z");
    expect(result[0].durationMs).toBe(3000);
  });
});
