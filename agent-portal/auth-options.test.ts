import { describe, it, expect, vi, afterEach } from "vitest";
import { refreshOnce } from "./auth-options";

afterEach(() => vi.unstubAllGlobals());

describe("refreshOnce", () => {
  it("shares a single backend refresh between concurrent requests", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ accessToken: "new-access", refreshToken: "new-refresh" }),
    }));
    vi.stubGlobal("fetch", fetchMock);
    const [a, b, c] = await Promise.all([
      refreshOnce("rt-1"),
      refreshOnce("rt-1"),
      refreshOnce("rt-1"),
    ]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(a).toEqual({ accessToken: "new-access", refreshToken: "new-refresh" });
    expect(b).toBe(a);
    expect(c).toBe(a);
  });

  it("returns null when the backend refuses the refresh", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, json: async () => ({}) })));
    expect(await refreshOnce("rt-refused")).toBeNull();
  });
});
