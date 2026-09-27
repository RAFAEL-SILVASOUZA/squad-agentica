import * as React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PipelinesPage from "./page";

// Mocks
const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

const mockToast = vi.fn();
vi.mock("@/components/ui/toast", () => ({
  useToast: () => ({ toast: mockToast }),
}));

const mockList = vi.fn();
vi.mock("@/lib/api", () => ({
  api: {
    list: (...args: unknown[]) => mockList(...args),
    post: vi.fn(),
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

const mockPipelines = [
  {
    id: "pipe-1",
    ownerId: "user-1",
    name: "Feature Dev Pipeline",
    description: "Full feature development",
    status: "draft" as const,
    entryNodeId: "node-1",
    nodes: [{ id: "node-1" }, { id: "node-2" }],
    edges: [{ id: "edge-1" }],
    currentCheckpoint: null,
    startedAt: null,
    completedAt: null,
  },
  {
    id: "pipe-2",
    ownerId: "user-1",
    name: "QA Pipeline",
    description: "",
    status: "running" as const,
    entryNodeId: "node-3",
    nodes: [{ id: "node-3" }],
    edges: [],
    currentCheckpoint: null,
    startedAt: "2026-01-01T00:00:00Z",
    completedAt: null,
  },
];

describe("PipelinesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading skeleton initially", () => {
    mockList.mockReturnValue(new Promise(() => {})); // never resolves
    render(<PipelinesPage />);
    // Skeleton elements should be present (4 skeleton cards)
    expect(document.querySelectorAll("[aria-hidden='true']").length).toBeGreaterThan(0);
  });

  it("renders pipeline cards when data is loaded", async () => {
    mockList.mockResolvedValue({
      items: mockPipelines,
      total: 2,
      page: 1,
      limit: 20,
    });

    render(<PipelinesPage />);

    await waitFor(() => {
      expect(screen.getByText("Feature Dev Pipeline")).toBeInTheDocument();
      expect(screen.getByText("QA Pipeline")).toBeInTheDocument();
    });

    // Check node/edge counts
    expect(screen.getByText("2 nós")).toBeInTheDocument();
    expect(screen.getByText("1 aresta")).toBeInTheDocument();
  });

  it("shows empty state when no pipelines", async () => {
    mockList.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      limit: 20,
    });

    render(<PipelinesPage />);

    await waitFor(() => {
      expect(screen.getByText("Nenhum pipeline ainda")).toBeInTheDocument();
    });

    expect(screen.getByText("Crie o primeiro pipeline para orquestrar agentes.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /criar primeiro pipeline/i })).toBeInTheDocument();
  });

  it("shows error state with retry on API failure", async () => {
    const { ApiError } = await import("@/lib/api");
    mockList.mockRejectedValue(new ApiError(500, { error: "internal error", code: "internal_error" }));

    render(<PipelinesPage />);

    await waitFor(() => {
      expect(screen.getByText("Falha ao carregar pipelines")).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: /de novo/i })).toBeInTheDocument();
  });

  it("navigates to pipeline detail on card click", async () => {
    mockList.mockResolvedValue({
      items: mockPipelines,
      total: 2,
      page: 1,
      limit: 20,
    });

    const user = userEvent.setup();
    render(<PipelinesPage />);

    await waitFor(() => {
      expect(screen.getByText("Feature Dev Pipeline")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Feature Dev Pipeline"));
    expect(mockPush).toHaveBeenCalledWith("/pipelines/pipe-1");
  });

  it("shows running badge for running pipeline", async () => {
    mockList.mockResolvedValue({
      items: mockPipelines,
      total: 2,
      page: 1,
      limit: 20,
    });

    render(<PipelinesPage />);

    await waitFor(() => {
      expect(screen.getByText("running")).toBeInTheDocument();
    });
  });
});
