import * as React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { act } from "react";
import { PipelineMonitor } from "./pipeline-monitor";
import { ToastProvider } from "@/components/ui/toast";
import { makePipeline, makeRun, makeCheckpoint } from "./test-fixtures";

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
        {((props as { nodes?: { id: string }[] }).nodes ?? []).map((n) => (
          <button
            key={n.id}
            data-testid={`rf-node-${n.id}`}
            onClick={(e) =>
              (props as { onNodeClick?: (e: unknown, n: unknown) => void }).onNodeClick?.(e, n)
            }
          />
        ))}
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

function openTab(name: RegExp | string) {
  fireEvent.click(screen.getByRole("tab", { name }));
}

function wsHandler(channel = "pipeline:status") {
  return mockWsClient.on.mock.calls.find((c) => c[0] === channel)?.[1] as (d: Record<string, unknown>) => void;
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
    window.history.replaceState(null, "", "/pipelines/pipe-1/run");
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
    // Agente de entrada tem input obrigatório: o modal pede o valor antes.
    fireEvent.change(await screen.findByLabelText("task *"), { target: { value: "gerar plano" } });
    fireEvent.click(screen.getByRole("button", { name: /^Executar$/ }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/pipelines/pipe-1/execute", {
        inputs: { task: "gerar plano" },
      });
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
    openTab("Histórico");

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

    openTab("Histórico");
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

    openTab("Histórico");
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

  it("restores a finished node output from its checkpoint when reopening the monitor", async () => {
    mockGet.mockResolvedValue(makePipeline());
    mockList
      .mockResolvedValueOnce({ items: [makeRun({ startedAt: "2026-01-01T10:00:00Z" })], total: 1, page: 1, limit: 50 })
      .mockResolvedValueOnce({
        items: [
          makeCheckpoint({
            nodeId: "node-1",
            status: "completed",
            timestamp: "2026-01-01T10:01:00Z",
            state: { data: { "node-1": { result: "especificação gerada" } } },
          }),
        ],
        total: 1,
        page: 1,
        limit: 50,
      });
    renderMonitor();
    // A aba Resultado (padrão) mostra a saída do nó, sem precisar clicar no grafo.
    const section = await screen.findByRole("region", { name: "Agent 1" });
    expect(within(section).getByText(/especificação gerada/)).toBeInTheDocument();
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

    openTab("Logs");
    // Filtros de log por agente e por nível
    expect(screen.getByLabelText("Filtrar por agente")).toBeInTheDocument();
    expect(screen.getByLabelText("Filtrar por nível")).toBeInTheDocument();
  });

  it("shows empty log message when no logs", async () => {
    const pipeline = makePipeline();

    mockGet.mockResolvedValue(pipeline);
    mockList
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 });

    renderMonitor();

    await screen.findByText("Test Pipeline");
    openTab("Logs");
    expect(screen.getByText("Aguardando logs da execução…")).toBeInTheDocument();
  });

  it("shows empty history message when no runs", async () => {
    const pipeline = makePipeline({ status: "draft" });

    mockGet.mockResolvedValue(pipeline);
    mockList
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 });

    renderMonitor();

    await screen.findByText("Test Pipeline");
    openTab("Histórico");
    expect(screen.getByText("Nenhuma execução ainda.")).toBeInTheDocument();
  });

  it("opens the read-only graph in a modal; clicking a node focuses its result", async () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    mockGet.mockResolvedValue(makePipeline());
    mockList
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 });

    renderMonitor();
    await screen.findByText("Test Pipeline");
    // O grafo não ocupa mais a página: só aparece no modal.
    expect(screen.queryByTestId("react-flow")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Ver grafo" }));
    const dialog = screen.getByRole("dialog", { name: /grafo/i });
    expect(within(dialog).getByTestId("react-flow")).toHaveAttribute("data-nodes", "2");

    fireEvent.click(within(dialog).getByTestId("rf-node-node-2"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Resultado" })).toHaveAttribute("aria-selected", "true");
    expect(scrollIntoView.mock.contexts.at(-1)).toBe(screen.getByRole("region", { name: "Agent 2" }));
  });

  it("shows the stage strip in graph order and live outputs as markdown in the Resultado tab", async () => {
    mockGet.mockResolvedValue(makePipeline());
    mockList
      .mockResolvedValueOnce({ items: [makeRun()], total: 1, page: 1, limit: 50 })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 });

    renderMonitor();
    await waitFor(() => expect(mockWsClient.connect).toHaveBeenCalled());
    const strip = screen.getByRole("list", { name: "Etapas" });
    expect(within(strip).getAllByRole("button").map((b) => b.textContent)).toEqual([
      expect.stringContaining("Agent 1"),
      expect.stringContaining("Agent 2"),
    ]);

    await act(async () => {
      wsHandler()({ pipelineId: "pipe-1", runId: "run-1", nodeId: "node-1", status: "completed", at: "" });
      wsHandler("agent:output")({ pipelineId: "pipe-1", nodeId: "node-1", output: { result: "# Plano\n\n- passo" } });
    });
    const section = screen.getByRole("region", { name: "Agent 1" });
    expect(within(section).getByRole("heading", { name: "Plano" })).toBeInTheDocument();
    expect(within(strip).getByRole("button", { name: /Agent 1.*Concluído/ })).toBeInTheDocument();
  });

  it("reloads the run on every aggregate status event so the PR link appears after publishing", async () => {
    mockGet.mockResolvedValue(makePipeline());
    mockList
      .mockResolvedValueOnce({ items: [makeRun()], total: 1, page: 1, limit: 50 })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 })
      // 1º "completed": run concluído, publicação ainda em andamento.
      .mockResolvedValueOnce({ items: [makeRun({ status: "completed", publishStatus: "none" })], total: 1, page: 1, limit: 50 })
      // 2º "completed" (após publicar): o run volta com o PR.
      .mockResolvedValueOnce({
        items: [makeRun({ status: "completed", publishStatus: "published", prUrl: "https://git/pr/7", prNumber: 7 })],
        total: 1,
        page: 1,
        limit: 50,
      });

    renderMonitor();
    await waitFor(() => expect(mockWsClient.connect).toHaveBeenCalled());
    await act(async () => {
      wsHandler()({ pipelineId: "pipe-1", runId: "run-1", nodeId: "", status: "completed", at: "" });
    });
    await waitFor(() => expect(mockList).toHaveBeenCalledTimes(3));
    expect(screen.queryByRole("link", { name: /PR #/ })).not.toBeInTheDocument();
    await act(async () => {
      wsHandler()({ pipelineId: "pipe-1", runId: "run-1", nodeId: "", status: "completed", at: "" });
    });
    expect(await screen.findByRole("link", { name: "PR #7" })).toHaveAttribute("href", "https://git/pr/7");
  });

  it("retries publishing via POST /api/runs/{id}/publish and shows the PR", async () => {
    mockGet.mockResolvedValue(makePipeline());
    mockList
      .mockResolvedValueOnce({
        items: [makeRun({ status: "completed", publishStatus: "failed", publishError: "push recusado" })],
        total: 1,
        page: 1,
        limit: 50,
      })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 });
    mockPost.mockResolvedValue(
      makeRun({ status: "completed", publishStatus: "published", prUrl: "https://git/pr/9", prNumber: 9 })
    );

    renderMonitor();
    expect(await screen.findByRole("alert")).toHaveTextContent("push recusado");
    fireEvent.click(screen.getByRole("button", { name: /Tentar publicar de novo/ }));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith("/api/runs/run-1/publish", {}));
    expect(await screen.findByRole("link", { name: "PR #9" })).toBeInTheDocument();
  });

  it("keeps the active tab in the URL and hides Arquivos without a run", async () => {
    window.history.replaceState(null, "", "/pipelines/pipe-1/run?tab=logs");
    mockGet.mockResolvedValue(makePipeline());
    mockList
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 });

    renderMonitor();
    await screen.findByText("Test Pipeline");
    expect(screen.getByRole("tab", { name: "Logs" })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByRole("tab", { name: "Arquivos do projeto" })).not.toBeInTheDocument();
    openTab("Histórico");
    expect(window.location.search).toBe("?tab=historico");
  });

  it("shows the Arquivos tab when there is a run", async () => {
    window.history.replaceState(null, "", "/pipelines/pipe-1/run?tab=arquivos");
    mockGet.mockImplementation(async (p: string) =>
      p.startsWith("/api/runs/")
        ? { items: [{ path: "README.md", size: 3, binary: false, status: "modified" }] }
        : makePipeline()
    );
    mockList
      .mockResolvedValueOnce({ items: [makeRun({ status: "completed" })], total: 1, page: 1, limit: 50 })
      .mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 50 });

    renderMonitor();
    expect(await screen.findByRole("button", { name: /README\.md/ })).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith("/api/runs/run-1/files");
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
    // Agente de entrada tem input obrigatório: o modal pede o valor antes.
    fireEvent.change(await screen.findByLabelText("task *"), { target: { value: "gerar plano" } });
    fireEvent.click(screen.getByRole("button", { name: /^Executar$/ }));

    await waitFor(() => {
      expect(screen.getByText(/já está em execução/i)).toBeInTheDocument();
    });
  });
});
