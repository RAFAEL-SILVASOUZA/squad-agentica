import * as React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import DashboardLayout from "./layout";
import { ToastProvider } from "@/components/ui/toast";

// ─── Mocks ───────────────────────────────────────────────────────────────────

const mockList = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    list: (...args: unknown[]) => mockList(...args),
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
  ApiError: class ApiError extends Error {},
  invalidateToken: vi.fn(),
}));

type WsHandler = (data: Record<string, unknown>) => void;
const wsHandlers = new Map<string, WsHandler[]>();

vi.mock("@/lib/websocket", () => ({
  getWebSocketClient: () => ({
    on: (channel: string, handler: WsHandler) => {
      const list = wsHandlers.get(channel) ?? [];
      list.push(handler);
      wsHandlers.set(channel, list);
    },
    off: vi.fn(),
    onReconnect: vi.fn(),
    connect: vi.fn(),
    disconnect: vi.fn(),
    setToken: vi.fn(),
  }),
  disposeWebSocketClient: vi.fn(),
}));

vi.mock("next-auth/react", () => ({
  useSession: () => ({
    data: { user: { name: "Test User" } },
    status: "authenticated",
  }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
  }),
}));

vi.mock("@/components/layout/app-shell", () => ({
  AppShell: ({
    children,
    pendingApprovals = 0,
  }: {
    children: React.ReactNode;
    pendingApprovals?: number;
    onNotificationsClick?: () => void;
  }) => (
    <div data-testid="app-shell" data-pending={pendingApprovals}>
      {children}
    </div>
  ),
}));

const mockFetch = vi.fn();

globalThis.fetch = mockFetch as unknown as typeof fetch;

function emitWs(channel: string, data: Record<string, unknown>) {
  for (const handler of wsHandlers.get(channel) ?? []) {
    void handler(data);
  }
}

function renderLayout() {
  return render(
    <ToastProvider>
      <DashboardLayout>
        <div>children</div>
      </DashboardLayout>
    </ToastProvider>
  );
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("DashboardLayout badge (fe-approvals, contrato §7)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    wsHandlers.clear();
    mockFetch.mockImplementation(async (url: string) => {
      if (String(url).includes("/api/session-token")) {
        return {
          ok: true,
          json: async () => ({ accessToken: "test-token" }),
        } as Response;
      }
      throw new Error(`unexpected fetch: ${String(url)}`);
    });
    mockList.mockResolvedValue({ items: [], total: 0, page: 1, limit: 1 });
  });

  it("shows initial pending count from REST", async () => {
    mockList.mockResolvedValue({ items: [], total: 3, page: 1, limit: 1 });
    renderLayout();
    await waitFor(() => {
      expect(screen.getByTestId("app-shell")).toHaveAttribute(
        "data-pending",
        "3"
      );
    });
  });

  it("increments badge on approval:new event", async () => {
    mockList.mockResolvedValue({ items: [], total: 2, page: 1, limit: 1 });
    renderLayout();
    await waitFor(() => {
      expect(wsHandlers.get("approval:new")).toHaveLength(1);
    });

    emitWs("approval:new", {
      approvalId: "appr-9",
      pipelineId: "pipe-1",
      runId: "run-1",
      nodeId: "node-1",
      message: "Aprovar?",
      at: "2026-09-26T10:00:00Z",
    });

    await waitFor(() => {
      expect(screen.getByTestId("app-shell")).toHaveAttribute(
        "data-pending",
        "3"
      );
    });
  });

  it("decrements badge on approval:resolved event", async () => {
    mockList.mockResolvedValue({ items: [], total: 2, page: 1, limit: 1 });
    renderLayout();
    await waitFor(() => {
      expect(wsHandlers.get("approval:resolved")).toHaveLength(1);
    });

    emitWs("approval:resolved", {
      approvalId: "appr-9",
      pipelineId: "pipe-1",
      runId: "run-1",
      nodeId: "node-1",
      decision: "approved",
      at: "2026-09-26T10:00:00Z",
    });

    await waitFor(() => {
      expect(screen.getByTestId("app-shell")).toHaveAttribute(
        "data-pending",
        "1"
      );
    });
  });

  it("never goes below zero on approval:resolved", async () => {
    mockList.mockResolvedValue({ items: [], total: 0, page: 1, limit: 1 });
    renderLayout();
    await waitFor(() => {
      expect(wsHandlers.get("approval:resolved")).toHaveLength(1);
    });

    emitWs("approval:resolved", {
      approvalId: "appr-9",
      pipelineId: "pipe-1",
      runId: "run-1",
      nodeId: "node-1",
      decision: "approved",
      at: "2026-09-26T10:00:00Z",
    });

    await waitFor(() => {
      expect(screen.getByTestId("app-shell")).toHaveAttribute(
        "data-pending",
        "0"
      );
    });
  });
});
