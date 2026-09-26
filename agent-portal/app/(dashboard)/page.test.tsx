import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import DashboardPage from "./page";
import { ToastProvider } from "@/components/ui/toast";
import type { Agent, ApprovalRequest, PipelineRun } from "@/lib/types";

// Mocks de lib/api e lib/websocket (contrato: mock de lib/api.ts e lib/websocket.ts).
vi.mock("@/lib/api", () => ({
  api: {
    list: vi.fn(),
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}));

vi.mock("@/lib/websocket", () => ({
  getWebSocketClient: vi.fn(),
  disposeWebSocketClient: vi.fn(),
}));

import { api } from "@/lib/api";
import { getWebSocketClient, disposeWebSocketClient } from "@/lib/websocket";

function makeAgent(overrides: Partial<Agent> = {}): Agent {
  return {
    id: "agent-1",
    ownerId: "owner-1",
    name: "Planner",
    type: "Planner",
    description: "",
    prompt: "",
    strategy: "",
    skills: [],
    tools: [],
    mcpServers: [],
    knowledge: [],
    integrations: [],
    inputs: [],
    outputs: [],
    actions: [],
    model: "gpt-4o",
    maxIterations: 10,
    timeout: 300,
    shellAccess: false,
    ...overrides,
  };
}

function makeApproval(overrides: Partial<ApprovalRequest> = {}): ApprovalRequest {
  return {
    id: "appr-1",
    pipelineId: "pipe-1",
    agentId: "agent-1",
    checkpointId: "cp-1",
    message: "Aprovar deploy?",
    context: {},
    status: "pending",
    channel: "in-app",
    sentAt: new Date().toISOString(),
    retryCount: 0,
    maxRetries: 3,
    attemptedChannels: ["in-app"],
    fallbackChannel: null,
    timeoutSeconds: 300,
    ...overrides,
  };
}

function makeRun(overrides: Partial<PipelineRun> = {}): PipelineRun {
  return {
    id: "run-1",
    pipelineId: "pipe-1",
    threadId: "thread-1",
    status: "running",
    startedAt: new Date().toISOString(),
    ...overrides,
  };
}

function mockWsClient() {
  const client = {
    on: vi.fn(),
    off: vi.fn(),
    onReconnect: vi.fn(),
    connect: vi.fn(),
    disconnect: vi.fn(),
    setToken: vi.fn(),
  };
  (getWebSocketClient as unknown as ReturnType<typeof vi.fn>).mockReturnValue(
    client
  );
  return client;
}

function renderPage() {
  return render(
    <ToastProvider>
      <DashboardPage />
    </ToastProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  // fetch do session-token (usado pelo efeito WS da página).
  // Devolve um token para que o WS conecte e registre os handlers.
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ accessToken: "test-token" }),
    })
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("DashboardPage", () => {
  it("renders empty state with CTA when portal is empty", async () => {
    (api.list as unknown as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 }) // agents
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 20 }); // approvals

    mockWsClient();
    renderPage();

    await waitFor(() => {
      expect(
        screen.getByText("Comece criando seu primeiro agente")
      ).toBeInTheDocument();
    });

    const cta = screen.getByRole("link", {
      name: /criar primeiro agente/i,
    });
    expect(cta).toHaveAttribute("href", "/agents/new");
    expect(screen.queryByText("Nenhum agente ainda")).not.toBeInTheDocument();
  });

  it("renders agent cards when agents exist", async () => {
    (api.list as unknown as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({
        items: [makeAgent({ name: "Planner", type: "Coordinador" })],
        total: 1,
        page: 1,
        limit: 50,
      })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 20 });

    mockWsClient();
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Coordinador")).toBeInTheDocument();
    });

    const link = screen.getByRole("link", { name: /abrir agente planner/i });
    expect(link).toHaveAttribute("href", "/agents/agent-1");
  });

  it("renders pending approvals list", async () => {
    (api.list as unknown as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 })
      .mockResolvedValueOnce({
        items: [makeApproval({ message: "Aprovar deploy?" })],
        total: 1,
        page: 1,
        limit: 20,
      });

    mockWsClient();
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Aprovar deploy?")).toBeInTheDocument();
    });
  });

  it("renders recent runs with status", async () => {
    const run = makeRun({ status: "running", startedAt: new Date().toISOString() });
    (api.list as unknown as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 })
      .mockResolvedValueOnce({
        items: [makeApproval({ pipelineId: "pipe-1" })],
        total: 1,
        page: 1,
        limit: 20,
      })
      .mockResolvedValueOnce({
        items: [run],
        total: 1,
        page: 1,
        limit: 20,
      });

    mockWsClient();
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Executando")).toBeInTheDocument();
    });
  });

  it("shows error with retry button when API fails", async () => {
    (api.list as unknown as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("boom")
    );

    mockWsClient();
    renderPage();

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /tentar novamente/i })
      ).toBeInTheDocument();
    });
  });

  it("renders stats strip with counts", async () => {
    const run = makeRun({ status: "completed", startedAt: new Date().toISOString() });
    (api.list as unknown as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 })
      .mockResolvedValueOnce({
        items: [makeApproval({ pipelineId: "pipe-1" })],
        total: 1,
        page: 1,
        limit: 20,
      })
      .mockResolvedValueOnce({
        items: [run],
        total: 1,
        page: 1,
        limit: 20,
      });

    mockWsClient();
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Runs concluídos")).toBeInTheDocument();
    });
  });

  it("updates run status on pipeline:status WS event", async () => {
    const run = makeRun({ status: "running", startedAt: new Date().toISOString() });
    (api.list as unknown as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 })
      .mockResolvedValueOnce({
        items: [makeApproval({ pipelineId: "pipe-1" })],
        total: 1,
        page: 1,
        limit: 20,
      })
      .mockResolvedValueOnce({
        items: [run],
        total: 1,
        page: 1,
        limit: 20,
      });

    const client = mockWsClient();
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Executando")).toBeInTheDocument();
    });

    // Simula evento WS pipeline:status → completed.
    const onStatus = client.on.mock.calls.find(
      (call) => call[0] === "pipeline:status"
    )?.[1] as (data: Record<string, unknown>) => void;
    expect(onStatus).toBeTypeOf("function");

    onStatus({
      pipelineId: "pipe-1",
      runId: run.id,
      nodeId: "node-1",
      status: "completed",
      at: new Date().toISOString(),
    });

    await waitFor(() => {
      expect(screen.getByText("Concluído")).toBeInTheDocument();
    });
  });

  it("refetches on WS reconnect", async () => {
    (api.list as unknown as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 20 });

    const client = mockWsClient();
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Comece criando seu primeiro agente")).toBeInTheDocument();
    });

    const onReconnect = client.onReconnect.mock.calls[0]?.[0] as () => void;
    expect(onReconnect).toBeTypeOf("function");

    // Refetch após reconexão.
    (api.list as unknown as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 20 });

    onReconnect();

    await waitFor(() => {
      expect(api.list).toHaveBeenCalledTimes(4);
    });
  });
});
