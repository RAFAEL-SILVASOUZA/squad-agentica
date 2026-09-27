import * as React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { act } from "react";
import { PipelineMonitor } from "./pipeline-monitor";
import { ToastProvider } from "@/components/ui/toast";
import type { Pipeline, PipelineRun, Checkpoint } from "@/lib/types";

// ─── Mocks ───────────────────────────────────────────────────────────────────

const mockGet = vi.fn();
const mockList = vi.fn();
const mockPost = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    get: (...args: unknown[]) => mockGet(...args),
    list: (...args: unknown[]) => mockList(...args),
    post: (...args: unknown[]) => mockPost(...args),
    put: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    status: number;
    code: string;
    details?: Record<string, unknown>;
    constructor(status: number, body: { error: string; code: string; details?: Record<string, unknown> }) {
      super(body.error);
      this.status = status;
      this.code = body.code;
      this.details = body.details;
    }
  },
}));

const mockWsClient = {
  on: vi.fn(),
  off: vi.fn(),
  onReconnect: vi.fn(),
  connect: vi.fn(),
  disconnect: vi.fn(),
  setToken: vi.fn(),
};

vi.mock("@/lib/websocket", () => ({
  getWebSocketClient: vi.fn(() => mockWsClient),
  disposeWebSocketClient: vi.fn(),
}));

// Mock @xyflow/react to avoid needing a real ReactFlow canvas in jsdom
vi.mock("@xyflow/react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@xyflow/react")>();
  return {
    ...actual,
    ReactFlow: ({ children, ...props }: { children?: React.ReactNode; [key: string]: unknown }) => (
      <div data-testid="react-flow" data-nodes={String((props as { nodes?: unknown[] }).nodes?.length ?? 0)}>
        {children}
      </div>
    ),
    useReactFlow: () => ({
      zoomIn: vi.fn(),
      zoomOut: vi.fn(),
      fitView: vi.fn(),
      screenToFlowPosition: vi.fn(() => ({ x: 0, y: 0 })),
    }),
    useNodesState: (initial: unknown[]) => {
      const [state, setState] = React.useState(initial);
      return [state, setState, vi.fn()];
    },
    useEdgesState: (initial: unknown[]) => {
      const [state, setState] = React.useState(initial);
      return [state, setState, vi.fn()];
    },
  };
});

// ─── Test data ───────────────────────────────────────────────────────────────

function makePipeline(overrides: Partial<Pipeline> = {}): Pipeline {
  return {
    id: "pipe-1",
    ownerId: "owner-1",
    name: "Test Pipeline",
    description: "A test pipeline",
    status: "draft",
    entryNodeId: "node-1",
    nodes: [
      {
        id: "node-1",
        agentId: "agent-1",
        position: { x: 100, y: 100 },
        label: "Agent 1",
        agentSnapshot: {
          agentId: "agent-1",
          version: 1,
          name: "Agent 1",
          description: "",
          prompt: "",
          strategy: "",
          skills: [],
          tools: [],
          mcpServers: [],
          knowledge: [],
          integrations: [],
          inputs: [{ name: "task", type: "string", required: true }],
          outputs: [{ name: "result", type: "string", required: true }],
          actions: ["follow"],
          model: "gpt-4o",
          maxIterations: 5,
          timeout: 300,
          shellAccess: false,
        },
      },
      {
        id: "node-2",
        agentId: "agent-2",
        position: { x: 300, y: 100 },
        label: "Agent 2",
        agentSnapshot: {
          agentId: "agent-2",
          version: 1,
          name: "Agent 2",
          description: "",
          prompt: "",
          strategy: "",
          skills: [],
          tools: [],
          mcpServers: [],
          knowledge: [],
          integrations: [],
          inputs: [{ name: "input", type: "string", required: true }],
          outputs: [{ name: "output", type: "string", required: true }],
          actions: ["finalize"],
          model: "gpt-4o",
          maxIterations: 3,
          timeout: 120,
          shellAccess: false,
        },
      },
    ],
    edges: [
      {
        id: "edge-1",
        type: "flow",
        source: "node-1",
        target: "node-2",
        requiresApproval: false,
      },
    ],
    currentCheckpoint: null,
    startedAt: null,
    completedAt: null,
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

function makeCheckpoint(overrides: Partial<Checkpoint> = {}): Checkpoint {
  return {
    id: "cp-1",
    pipelineId: "pipe-1",
    nodeId: "node-1",
    state: {},
    timestamp: new Date().toISOString(),
    status: "completed",
    metadata: {},
    ...overrides,
  };
}

function mockFetchToken() {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ accessToken: "test-token" }),
    })
  );
}

function renderMonitor(pipelineId = "pipe-1") {
  return render(
    <ToastProvider>
      <PipelineMonitor pipelineId={pipelineId} />
    </ToastProvider>
  );
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("PipelineMonitor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchToken();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows loading skeleton initially", () => {
    mockGet.mockReturnValue(new Promise(() => {}));
    mockList.mockReturnValue(new Promise(() => {}));
    renderMonitor();
    // Should show skeleton (no pipeline name yet)
    expect(screen.queryByText("Test Pipeline")).not.toBeInTheDocument();
  });

  it("renders pipeline name and action buttons", async () => {
    const pipeline = makePipeline();
    const run = makeRun({ status: "running" });

    mockGet.mockResolvedValue(pipeline);
    mockList
      .mockResolvedValueOnce({ items: [run], total: 1, page: 1, limit: 50 }) // runs
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 }); // checkpoints

    renderMonitor();

    await waitFor(() => {
      expect(screen.getByText("Test Pipeline")).toBeInTheDocument();
    });

    // Running pipeline: should show Pause and Stop buttons
    expect(screen.getByRole("button", { name: /pausar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /parar/i })).toBeInTheDocument();
    // Should NOT show Iniciar (already running)
    expect(screen.queryByRole("button", { name: /iniciar/i })).not.toBeInTheDocument();
  });

  it("shows Iniciar button when pipeline is not running", async () => {
    const pipeline = makePipeline({ status: "draft" });

    mockGet.mockResolvedValue(pipeline);
    mockList
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 }) // runs
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 }); // checkpoints

    renderMonitor();

    await waitFor(() => {
      expect(screen.getByText("Test Pipeline")).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: /iniciar/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /pausar/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /parar/i })).not.toBeInTheDocument();
  });

  it("shows Retomar button when pipeline is paused", async () => {
    const pipeline = makePipeline({ status: "paused" });
    const run = makeRun({ status: "paused" });

    mockGet.mockResolvedValue(pipeline);
    mockList
      .mockResolvedValueOnce({ items: [run], total: 1, page: 1, limit: 50 })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 });

    renderMonitor();

    await waitFor(() => {
      expect(screen.getByText("Test Pipeline")).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: /retomar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /parar/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /iniciar/i })).not.toBeInTheDocument();
  });

  it("shows not found state for 404", async () => {
    const { ApiError } = await import("@/lib/api");
    mockGet.mockRejectedValue(
      new ApiError(404, { error: "not found", code: "pipeline_not_found" })
    );
    mockList.mockResolvedValue({ items: [], total: 0, page: 1, limit: 50 });

    renderMonitor();

    await waitFor(() => {
      expect(screen.getByText("Pipeline não encontrada")).toBeInTheDocument();
    });
  });

  it("shows error state with retry on API failure", async () => {
    const { ApiError } = await import("@/lib/api");
    mockGet.mockRejectedValue(
      new ApiError(500, { error: "internal error", code: "internal_error" })
    );
    mockList.mockResolvedValue({ items: [], total: 0, page: 1, limit: 50 });

    renderMonitor();

    await waitFor(() => {
      expect(screen.getByText("Falha ao carregar o monitor")).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: /tentar novamente/i })).toBeInTheDocument();
  });

  it("calls execute endpoint when Iniciar is clicked", async () => {
    const pipeline = makePipeline({ status: "draft" });

    mockGet.mockResolvedValue(pipeline);
    mockList
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 }) // initial runs
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 }) // initial checkpoints
      .mockResolvedValueOnce({ items: [makeRun()], total: 1, page: 1, limit: 50 }); // after execute

    mockPost.mockResolvedValue({});

    renderMonitor();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /iniciar/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /iniciar/i }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/pipelines/pipe-1/execute", {});
    });
  });

  it("calls pause endpoint when Pausar is clicked", async () => {
    const pipeline = makePipeline({ status: "running" });
    const run = makeRun({ status: "running" });

    mockGet.mockResolvedValue(pipeline);
    mockList
      .mockResolvedValueOnce({ items: [run], total: 1, page: 1, limit: 50 })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 });

    mockPost.mockResolvedValue({});

    renderMonitor();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /pausar/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /pausar/i }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/pipelines/pipe-1/pause", {});
    });
  });

  it("calls stop endpoint when Parar is clicked", async () => {
    const pipeline = makePipeline({ status: "running" });
    const run = makeRun({ status: "running" });

    mockGet.mockResolvedValue(pipeline);
    mockList
      .mockResolvedValueOnce({ items: [run], total: 1, page: 1, limit: 50 })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 });

    mockPost.mockResolvedValue({});

    renderMonitor();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /parar/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /parar/i }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/pipelines/pipe-1/stop", {});
    });
  });

  it("shows run history with status badges", async () => {
    const pipeline = makePipeline({ status: "completed" });
    const runs = [
      makeRun({ id: "run-1", status: "completed", startedAt: "2026-01-01T10:00:00Z" }),
      makeRun({ id: "run-2", status: "failed", startedAt: "2026-01-02T10:00:00Z" }),
    ];

    mockGet.mockResolvedValue(pipeline);
    mockList
      .mockResolvedValueOnce({ items: runs, total: 2, page: 1, limit: 50 })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 });

    renderMonitor();

    await waitFor(() => {
      expect(screen.getByText("Test Pipeline")).toBeInTheDocument();
    });

    // Should show both runs in history (use getAllByText because legend also has these labels)
    expect(screen.getAllByText("Concluído").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Falhou").length).toBeGreaterThanOrEqual(1);
  });

  it("shows checkpoints with resume button for interrupted/failed", async () => {
    const pipeline = makePipeline({ status: "failed" });
    const checkpoints = [
      makeCheckpoint({ id: "cp-1", status: "completed" }),
      makeCheckpoint({ id: "cp-2", status: "interrupted", nodeId: "node-2" }),
      makeCheckpoint({ id: "cp-3", status: "failed", nodeId: "node-2" }),
    ];

    mockGet.mockResolvedValue(pipeline);
    mockList
      .mockResolvedValueOnce({ items: [makeRun({ status: "failed" })], total: 1, page: 1, limit: 50 })
      .mockResolvedValueOnce({ items: checkpoints, total: 3, page: 1, limit: 50 });

    mockPost.mockResolvedValue({});

    renderMonitor();

    await waitFor(() => {
      expect(screen.getByText("Test Pipeline")).toBeInTheDocument();
    });

    // Should show "Retomar" buttons for interrupted and failed checkpoints
    const resumeButtons = screen.getAllByRole("button", { name: /retomar/i });
    expect(resumeButtons.length).toBeGreaterThanOrEqual(2);
  });

  it("calls checkpoint resume endpoint when Retomar checkpoint is clicked", async () => {
    const pipeline = makePipeline({ status: "failed" });
    const checkpoints = [
      makeCheckpoint({ id: "cp-2", status: "interrupted", nodeId: "node-2" }),
    ];

    mockGet.mockResolvedValue(pipeline);
    mockList
      .mockResolvedValueOnce({ items: [makeRun({ status: "failed" })], total: 1, page: 1, limit: 50 })
      .mockResolvedValueOnce({ items: checkpoints, total: 1, page: 1, limit: 50 });

    mockPost.mockResolvedValue({});

    renderMonitor();

    await waitFor(() => {
      expect(screen.getByText("Test Pipeline")).toBeInTheDocument();
    });

    const resumeBtn = screen.getByRole("button", { name: /retomar/i });
    fireEvent.click(resumeBtn);

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        "/api/pipelines/pipe-1/checkpoints/cp-2/resume",
        {}
      );
    });
  });

  it("registers WS handlers for pipeline events", async () => {
    const pipeline = makePipeline();

    mockGet.mockResolvedValue(pipeline);
    mockList
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 });

    renderMonitor();

    await waitFor(() => {
      expect(screen.getByText("Test Pipeline")).toBeInTheDocument();
    });

    // Wait for WS connection
    await waitFor(() => {
      expect(mockWsClient.connect).toHaveBeenCalled();
    });

    // Should have registered handlers for all 5 channels
    const channels = mockWsClient.on.mock.calls.map((call) => call[0]);
    expect(channels).toContain("pipeline:status");
    expect(channels).toContain("pipeline:log");
    expect(channels).toContain("agent:output");
    expect(channels).toContain("approval:new");
    expect(channels).toContain("approval:resolved");
  });

  it("shows the failure reason when the aggregated run status arrives as failed", async () => {
    const pipeline = makePipeline();
    mockGet.mockResolvedValue(pipeline);
    mockList
      .mockResolvedValueOnce({ items: [makeRun()], total: 1, page: 1, limit: 50 })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 })
      // refetch após o status agregado: o run volta com o erro gravado.
      .mockResolvedValueOnce({
        items: [makeRun({ status: "failed", error: "Missing tool call type" })],
        total: 1,
        page: 1,
        limit: 50,
      });

    renderMonitor();
    await waitFor(() => expect(mockWsClient.connect).toHaveBeenCalled());
    const onStatus = mockWsClient.on.mock.calls.find((c) => c[0] === "pipeline:status")?.[1] as (
      d: Record<string, unknown>
    ) => void;
    await act(async () => {
      onStatus({ pipelineId: "pipe-1", runId: "run-1", nodeId: "", status: "failed", at: "" });
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("Missing tool call type");
  });

  it("filters logs by node", async () => {
    const pipeline = makePipeline();

    mockGet.mockResolvedValue(pipeline);
    mockList
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 });

    renderMonitor();

    await waitFor(() => {
      expect(screen.getByText("Test Pipeline")).toBeInTheDocument();
    });

    // The log filter select should be present
    const nodeFilter = screen.getByLabelText("Filtrar por nó");
    expect(nodeFilter).toBeInTheDocument();
  });

  it("shows empty log message when no logs", async () => {
    const pipeline = makePipeline();

    mockGet.mockResolvedValue(pipeline);
    mockList
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 });

    renderMonitor();

    await waitFor(() => {
      expect(screen.getByText("Aguardando logs da execução…")).toBeInTheDocument();
    });
  });

  it("shows empty history message when no runs", async () => {
    const pipeline = makePipeline({ status: "draft" });

    mockGet.mockResolvedValue(pipeline);
    mockList
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 });

    renderMonitor();

    await waitFor(() => {
      expect(screen.getByText("Nenhuma execução ainda.")).toBeInTheDocument();
    });
  });

  it("shows node panel hint when no node selected", async () => {
    const pipeline = makePipeline();

    mockGet.mockResolvedValue(pipeline);
    mockList
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 });

    renderMonitor();

    await waitFor(() => {
      expect(
        screen.getByText("Clique em um nó no grafo para ver detalhes.")
      ).toBeInTheDocument();
    });
  });

  it("shows 409 toast when execute fails with pipeline_already_running", async () => {
    const { ApiError } = await import("@/lib/api");
    const pipeline = makePipeline({ status: "draft" });

    mockGet.mockResolvedValue(pipeline);
    mockList
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 });

    mockPost.mockRejectedValue(
      new ApiError(409, { error: "pipeline already running", code: "pipeline_already_running" })
    );

    renderMonitor();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /iniciar/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /iniciar/i }));

    await waitFor(() => {
      expect(screen.getByText(/já está em execução/i)).toBeInTheDocument();
    });
  });
});
