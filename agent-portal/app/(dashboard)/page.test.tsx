import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import DashboardPage from "./page";
import { ToastProvider } from "@/components/ui/toast";
import { filterAgentsBySearchAndType } from "@/lib/agent-filter";
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

    // O card leva href=/agents/agent-1 e mostra o tipo do agente.
    // (O select de filtro também lista o tipo; por isso usamos o link por href.)
    await waitFor(() => {
      const link = screen
        .getAllByRole("link")
        .find((el) => el.getAttribute("href") === "/agents/agent-1");
      expect(link).not.toBeUndefined();
      expect(link?.textContent).toContain("Coordinador");
    });
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

  it("filters agents client-side by search term", async () => {
    (api.list as unknown as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({
        items: [
          makeAgent({ id: "a1", name: "Planner", type: "Coordinador" }),
          makeAgent({
            id: "a2",
            name: "Backend Developer",
            type: "Developer",
            description: "Escreve APIs REST",
          }),
        ],
        total: 2,
        page: 1,
        limit: 50,
      })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 20 });

    mockWsClient();
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Planner")).toBeInTheDocument();
      expect(screen.getByText("Backend Developer")).toBeInTheDocument();
    });

    const search = screen.getByLabelText("Buscar agente");
    fireEvent.change(search, { target: { value: "api" } });

    await waitFor(() => {
      expect(screen.queryByText("Planner")).not.toBeInTheDocument();
      expect(screen.getByText("Backend Developer")).toBeInTheDocument();
    });
  });

  it("filters agents by type via the type selector (server-side param)", async () => {
    (api.list as unknown as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({
        items: [
          makeAgent({ id: "a1", name: "Planner", type: "Coordinador" }),
          makeAgent({ id: "a2", name: "Dev", type: "Developer" }),
        ],
        total: 2,
        page: 1,
        limit: 50,
      })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 20 });

    mockWsClient();
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Planner")).toBeInTheDocument();
    });

    const typeFilter = screen.getByLabelText("Filtrar por tipo");
    fireEvent.change(typeFilter, { target: { value: "Developer" } });

    // A chamada de refetch leva type=Developer.
    await waitFor(() => {
      const calls = (api.list as unknown as ReturnType<typeof vi.fn>).mock.calls
        .filter((c: unknown[]) => c[0] === "/api/agents");
      expect(calls[calls.length - 1][1]).toEqual(
        expect.objectContaining({
          query: expect.objectContaining({ type: "Developer" }),
        })
      );
    });
  });

  it("shows a no-match empty state with a clear-filters action", async () => {
    (api.list as unknown as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({
        items: [makeAgent({ id: "a1", name: "Planner", type: "Coordinador" })],
        total: 1,
        page: 1,
        limit: 50,
      })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 20 });

    mockWsClient();
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Planner")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Buscar agente"), {
      target: { value: "zzz" },
    });

    await waitFor(() => {
      expect(screen.getByText("Nenhum agente encontrado")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /limpar filtros/i }));

    await waitFor(() => {
      expect(screen.getByText("Planner")).toBeInTheDocument();
    });
  });
});

describe("filterAgentsBySearchAndType", () => {
  const agents: Agent[] = [
    makeAgent({ id: "a1", name: "Planner", type: "Coordinador", description: "Monta o plano" }),
    makeAgent({ id: "a2", name: "Dev", type: "Developer", description: "APIs" }),
  ];

  it("returns all agents when search and filter are empty", () => {
    expect(filterAgentsBySearchAndType(agents, "", "")).toHaveLength(2);
  });

  it("matches name, description and type case-insensitively", () => {
    expect(filterAgentsBySearchAndType(agents, "plano", "")).toHaveLength(1);
    expect(filterAgentsBySearchAndType(agents, "apis", "")).toHaveLength(1);
    expect(filterAgentsBySearchAndType(agents, "coordinador", "")).toHaveLength(1);
  });

  it("combines type filter and search", () => {
    expect(filterAgentsBySearchAndType(agents, "dev", "Developer")).toHaveLength(1);
    expect(filterAgentsBySearchAndType(agents, "dev", "Coordinador")).toHaveLength(0);
  });
});
