import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { usePaletteData } from "./use-palette-data";

const mockList = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    list: (...args: unknown[]) => mockList(...args),
  },
}));

function paginated<T>(items: T[]): { items: T[]; total: number; page: number; limit: number } {
  return { items, total: items.length, page: 1, limit: 50 };
}

/** Mock path-aware: agentes e pipelines com 1 item, demais vazios. `failPaths` rejeitam. */
function mockByPath(failPaths: string[] = []) {
  mockList.mockImplementation(async (path: string) => {
    if (failPaths.includes(path)) throw new Error("boom");
    switch (path) {
      case "/api/agents":
        return paginated([{ id: "a1", name: "Redator de Especificações" }]);
      case "/api/pipelines":
        return paginated([{ id: "p1", name: "Build" }]);
      default:
        return paginated([]);
    }
  });
}

describe("usePaletteData", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("carrega grupos de Agentes e Pipelines quando open", async () => {
    mockByPath();
    const { result } = renderHook(() => usePaletteData(true));
    await waitFor(() => expect(result.current.loading).toBe(false));

    const agents = result.current.groups.find((g) => g.type === "agents");
    const pipelines = result.current.groups.find((g) => g.type === "pipelines");

    expect(agents?.label).toBe("Agentes");
    expect(agents?.items).toEqual([
      { id: "a1", name: "Redator de Especificações", type: "agents", href: "/agents/a1" },
    ]);
    expect(pipelines?.label).toBe("Pipelines");
    expect(pipelines?.items).toEqual([
      { id: "p1", name: "Build", type: "pipelines", href: "/pipelines/p1" },
    ]);
  });

  it("loading começa true e vira false após o load", async () => {
    mockByPath();
    const { result } = renderHook(() => usePaletteData(true));
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
  });

  it("um endpoint que falha não impede os demais (Promise.allSettled)", async () => {
    mockByPath(["/api/agents"]);
    const { result } = renderHook(() => usePaletteData(true));
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.groups.find((g) => g.type === "agents")).toBeUndefined();
    const pipelines = result.current.groups.find((g) => g.type === "pipelines");
    expect(pipelines?.items).toEqual([
      { id: "p1", name: "Build", type: "pipelines", href: "/pipelines/p1" },
    ]);
  });
});
