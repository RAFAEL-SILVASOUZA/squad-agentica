import * as React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import PipelineDetailPage from "./page";

// Mocks
const mockPush = vi.fn();
const mockParams = { id: "pipe-1" };

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  useParams: () => mockParams,
}));

const mockToast = vi.fn();
vi.mock("@/components/ui/toast", () => ({
  useToast: () => ({ toast: mockToast }),
}));

const mockGet = vi.fn();
const mockPut = vi.fn();
const mockList = vi.fn();
vi.mock("@/lib/api", () => ({
  api: {
    get: (...args: unknown[]) => mockGet(...args),
    put: (...args: unknown[]) => mockPut(...args),
    list: (...args: unknown[]) => mockList(...args),
  },
  ApiError: class ApiError extends Error {
    status: number;
    code: string;
    constructor(status: number, body: { error: string; code: string }) {
      super(body.error);
      this.status = status;
      this.code = body.code;
    }
  },
}));

// Mock FlowEditor
vi.mock("@/components/FlowEditor", () => ({
  FlowEditor: ({ pipeline, onSave, onEdgeSelect, disabled }: {
    pipeline: unknown;
    onSave: (nodes: unknown[], edges: unknown[]) => Promise<void>;
    onEdgeSelect?: (edge: unknown) => void;
    disabled?: boolean;
  }) => (
    <div data-testid="flow-editor" data-disabled={String(disabled)}>
      <span data-testid="pipeline-name">{(pipeline as { name: string }).name}</span>
      <button data-testid="mock-save" onClick={() => onSave([], [])}>Mock Save</button>
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
        actions: [],
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
      expect(screen.getByText("Pipeline not found")).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: /back to pipelines/i })).toBeInTheDocument();
  });

  it("shows error state with retry on API failure", async () => {
    const { ApiError } = await import("@/lib/api");
    mockGet.mockRejectedValue(new ApiError(500, { error: "internal error", code: "internal_error" }));
    mockList.mockResolvedValue({ items: [], total: 0, page: 1, limit: 100 });

    render(<PipelineDetailPage />);

    await waitFor(() => {
      expect(screen.getByText("Failed to load pipeline")).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
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

    render(<PipelineDetailPage />);

    await waitFor(() => {
      expect(screen.getByTestId("flow-editor")).toBeInTheDocument();
    });

    const monitorBtn = screen.getByRole("button", { name: /view pipeline monitor/i });
    monitorBtn.click();
    expect(mockPush).toHaveBeenCalledWith("/pipelines/pipe-1/run");
  });
});
