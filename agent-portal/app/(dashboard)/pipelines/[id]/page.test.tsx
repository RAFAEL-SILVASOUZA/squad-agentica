import * as React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PipelineDetailPage from "./page";

// Mocks
const mockPush = vi.fn();
const mockParams = { id: "pipe-1" };

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  useParams: () => mockParams,
  useSearchParams: () => new URLSearchParams(),
}));

const mockAddToast = vi.fn();
vi.mock("@/components/ui/toast", () => ({
  useToast: () => ({ addToast: mockAddToast }),
}));

const mockGet = vi.fn();
const mockPut = vi.fn();
const mockPost = vi.fn();
const mockList = vi.fn();
vi.mock("@/lib/api", () => ({
  api: {
    get: (...args: unknown[]) => mockGet(...args),
    put: (...args: unknown[]) => mockPut(...args),
    post: (...args: unknown[]) => mockPost(...args),
    list: (...args: unknown[]) => mockList(...args),
  },
  ApiError: class ApiError extends Error {
    status: number;
    code: string;
    details?: Record<string, unknown>;
    constructor(status: number, body: { error: string; code: string }) {
      super(body.error);
      this.status = status;
      this.code = body.code;
    }
  },
}));

// Mock FlowEditor: expoe onGraphChange para o teste de validacao em tempo real
type MockFlowEditorProps = {
  pipeline: unknown;
  onSave: (nodes: unknown[], edges: unknown[]) => Promise<void>;
  onEdgeSelect?: (edge: unknown) => void;
  onEdgeChange?: (edge: unknown) => void;
  onGraphChange?: (nodes: unknown[], edges: unknown[]) => void;
  edgePanelSlot?: React.ReactNode;
  errorIdSets?: { nodeIds: Set<string>; edgeIds: Set<string> };
  disabled?: boolean;
};

vi.mock("@/components/FlowEditor", () => ({
  FlowEditor: (props: MockFlowEditorProps) => (
    <div
      data-testid="flow-editor"
      data-disabled={String(!!props.disabled)}
      data-node-errors={props.errorIdSets ? [...props.errorIdSets.nodeIds].join(",") : ""}
      data-edge-errors={props.errorIdSets ? [...props.errorIdSets.edgeIds].join(",") : ""}
    >
      <span data-testid="pipeline-name">{(props.pipeline as { name: string }).name}</span>
      <button data-testid="mock-save" onClick={() => props.onSave([], [])}>Mock Save</button>
      <button
        data-testid="mock-add-orphan"
        onClick={() =>
          props.onGraphChange?.(
            [(props.pipeline as { nodes: unknown[] }).nodes[0], { id: "orphan", agentId: "a", position: { x: 0, y: 0 }, agentSnapshot: { name: "Orfan", inputs: [], outputs: [], actions: [] } }],
            []
          )
        }
      >
        Mock add orphan
      </button>
      {props.edgePanelSlot}
    </div>
  ),
}));

vi.mock("@/components/EdgePanel", () => ({
  EdgePanel: ({ edge, onClose }: { edge: { id: string }; onClose: () => void }) => (
    <div data-testid="edge-panel">
      <span data-testid="edge-panel-id">{edge.id}</span>
      <button onClick={onClose}>close panel</button>
    </div>
  ),
}));

const mockPipeline = {
  id: "pipe-1",
  ownerId: "user-1",
  name: "Test Pipeline",
  description: "A test pipeline",
  status: "draft" as const,
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
        inputs: [],
        outputs: [],
        actions: ["follow"],
        model: "gpt-4o",
        maxIterations: 5,
        timeout: 300,
        shellAccess: false,
      },
    },
  ],
  edges: [],
  currentCheckpoint: null,
  startedAt: null,
  completedAt: null,
};

const mockAgents = [
  {
    id: "agent-1",
    ownerId: "user-1",
    name: "Agent 1",
    type: "Developer",
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
    maxIterations: 5,
    timeout: 300,
    shellAccess: false,
  },
];

describe("PipelineDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading skeleton initially", () => {
    mockGet.mockReturnValue(new Promise(() => {}));
    mockList.mockReturnValue(new Promise(() => {}));
    render(<PipelineDetailPage />);
    // Should show skeleton (no pipeline name yet)
    expect(screen.queryByTestId("flow-editor")).not.toBeInTheDocument();
  });

  it("renders FlowEditor with pipeline data", async () => {
    mockGet.mockResolvedValue(mockPipeline);
    mockList.mockResolvedValue({ items: mockAgents, total: 1, page: 1, limit: 100 });

    render(<PipelineDetailPage />);

    await waitFor(() => {
      expect(screen.getByTestId("flow-editor")).toBeInTheDocument();
    });

    expect(screen.getByTestId("pipeline-name")).toHaveTextContent("Test Pipeline");
    expect(screen.getAllByText("Test Pipeline").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("A test pipeline")).toBeInTheDocument();
  });

  it("shows not found state for 404", async () => {
    const { ApiError } = await import("@/lib/api");
    mockGet.mockRejectedValue(new ApiError(404, { error: "not found", code: "pipeline_not_found" }));
    mockList.mockResolvedValue({ items: [], total: 0, page: 1, limit: 100 });

    render(<PipelineDetailPage />);

    await waitFor(() => {
      expect(screen.getByText("Pipeline não encontrado")).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: /voltar para pipelines/i })).toBeInTheDocument();
  });

  it("shows error state with retry on API failure", async () => {
    const { ApiError } = await import("@/lib/api");
    mockGet.mockRejectedValue(new ApiError(500, { error: "internal error", code: "internal_error" }));
    mockList.mockResolvedValue({ items: [], total: 0, page: 1, limit: 100 });

    render(<PipelineDetailPage />);

    await waitFor(() => {
      expect(screen.getByText("Falha ao carregar o pipeline")).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: /de novo/i })).toBeInTheDocument();
  });

  it("disables editor when pipeline is running", async () => {
    const runningPipeline = { ...mockPipeline, status: "running" as const };
    mockGet.mockResolvedValue(runningPipeline);
    mockList.mockResolvedValue({ items: mockAgents, total: 1, page: 1, limit: 100 });

    render(<PipelineDetailPage />);

    await waitFor(() => {
      expect(screen.getByTestId("flow-editor")).toBeInTheDocument();
    });

    expect(screen.getByTestId("flow-editor")).toHaveAttribute("data-disabled", "true");
  });

  it("enables editor when pipeline is draft", async () => {
    mockGet.mockResolvedValue(mockPipeline);
    mockList.mockResolvedValue({ items: mockAgents, total: 1, page: 1, limit: 100 });

    render(<PipelineDetailPage />);

    await waitFor(() => {
      expect(screen.getByTestId("flow-editor")).toBeInTheDocument();
    });

    expect(screen.getByTestId("flow-editor")).toHaveAttribute("data-disabled", "false");
  });

  it("navigates to monitor page", async () => {
    mockGet.mockResolvedValue(mockPipeline);
    mockList.mockResolvedValue({ items: mockAgents, total: 1, page: 1, limit: 100 });
    mockPost.mockResolvedValue({ valid: true, errors: [] });

    render(<PipelineDetailPage />);

    await waitFor(() => {
      expect(screen.getByTestId("flow-editor")).toBeInTheDocument();
    });

    const monitorBtn = screen.getByRole("button", { name: /ver monitor do pipeline/i });
    monitorBtn.click();
    expect(mockPush).toHaveBeenCalledWith("/pipelines/pipe-1/run");
  });

  describe("validacao + executar (fe-flow-edges)", () => {
    beforeEach(() => {
      // padrao: validacao de servidor ok
      mockPost.mockResolvedValue({ valid: true, errors: [] });
      mockPut.mockImplementation(async (_path: string, body: { entryNodeId: string }) => body);
    });

    it("mostra 'Grafo válido' para grafo valido e habilita Executar", async () => {
      mockGet.mockResolvedValue(mockPipeline);
      mockList.mockResolvedValue({ items: mockAgents, total: 1, page: 1, limit: 100 });

      render(<PipelineDetailPage />);

      await waitFor(() => {
        expect(screen.getByText("Grafo válido")).toBeInTheDocument();
      }, { timeout: 3000 });

      expect(screen.getByRole("button", { name: /executar pipeline/i })).toBeEnabled();
    });

    it("bloqueia Executar e destaca no com erro quando o grafo fica invalido", async () => {
      mockGet.mockResolvedValue(mockPipeline);
      mockList.mockResolvedValue({ items: mockAgents, total: 1, page: 1, limit: 100 });

      render(<PipelineDetailPage />);

      await waitFor(() => {
        expect(screen.getByText("Grafo válido")).toBeInTheDocument();
      }, { timeout: 3000 });

      // Simula adicao de um no orfao pelo canvas
      screen.getByTestId("mock-add-orphan").click();

      await waitFor(() => {
        expect(screen.getByText(/erro de validação/)).toBeInTheDocument();
      }, { timeout: 3000 });

      const execBtn = screen.getByRole("button", { name: /executar pipeline/i });
      expect(execBtn).toBeDisabled();

      // O no com erro e destacado no canvas (errorIdSets.nodeIds)
      expect(screen.getByTestId("flow-editor")).toHaveAttribute("data-node-errors", "orphan");
    });

    it("Executar salva o grafo, cria o run e navega para o monitor", async () => {
      mockGet.mockResolvedValue(mockPipeline);
      mockList.mockResolvedValue({ items: mockAgents, total: 1, page: 1, limit: 100 });
      mockPost.mockResolvedValue({ runId: "run-1", status: "running" });

      render(<PipelineDetailPage />);

      await waitFor(() => {
        expect(screen.getByText("Grafo válido")).toBeInTheDocument();
      }, { timeout: 3000 });

      await userEvent.click(screen.getByRole("button", { name: /executar pipeline/i }));

      await waitFor(() => {
        expect(mockPost).toHaveBeenCalledWith("/api/pipelines/pipe-1/execute", { inputs: {} });
      });
      // Depois de executar, o monitor abre direto na aba Resultado.
      expect(mockPush).toHaveBeenCalledWith("/pipelines/pipe-1/run?tab=resultado");
    });

    it("409 no execute vira toast e nao navega", async () => {
      const { ApiError } = await import("@/lib/api");
      mockGet.mockResolvedValue(mockPipeline);
      mockList.mockResolvedValue({ items: mockAgents, total: 1, page: 1, limit: 100 });
      mockPut.mockResolvedValue(mockPipeline);
      mockPost.mockImplementation(async (path: string) => {
        if (path === "/api/pipelines/validate") return { valid: true, errors: [] };
        throw new ApiError(409, { error: "pipeline already running", code: "pipeline_already_running" });
      });

      render(<PipelineDetailPage />);

      await waitFor(() => {
        expect(screen.getByText("Grafo válido")).toBeInTheDocument();
      }, { timeout: 3000 });

      await userEvent.click(screen.getByRole("button", { name: /executar pipeline/i }));

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith("error", expect.stringMatching(/já está em execução/i));
      });
      expect(mockPush).not.toHaveBeenCalledWith(expect.stringContaining("/pipelines/pipe-1/run"));
    });

    it("fallback: se o endpoint de validacao nao existe (404), usa validacao local", async () => {
      const { ApiError } = await import("@/lib/api");
      mockGet.mockResolvedValue(mockPipeline);
      mockList.mockResolvedValue({ items: mockAgents, total: 1, page: 1, limit: 100 });
      mockPost.mockRejectedValue(new ApiError(404, { error: "not found", code: "not_found" }));

      render(<PipelineDetailPage />);

      // Grafo localmente valido => mesmo com o endpoint ausente, o status finaliza como valido
      await waitFor(() => {
        expect(screen.getByText("Grafo válido")).toBeInTheDocument();
      }, { timeout: 3000 });
    });
  });
});
