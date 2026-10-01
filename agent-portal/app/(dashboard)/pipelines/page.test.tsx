import * as React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import PipelinesPage from "./page";

// jsdom não tem matchMedia; mock para o DataTable (mobile detection).
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mocks
const mockPush = vi.fn();
const mockReplace = vi.fn();
let mockRunParam = "";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
  useSearchParams: () => new URLSearchParams(mockRunParam ? `run=${mockRunParam}` : ""),
}));

const mockAddToast = vi.fn();
vi.mock("@/components/ui/toast", () => ({
  useToast: () => ({ addToast: mockAddToast }),
}));

const mockList = vi.fn();
const mockPost = vi.fn();
const mockDelete = vi.fn();
vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  api: {
    list: (...args: unknown[]) => mockList(...args),
    post: (...args: unknown[]) => mockPost(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
    put: vi.fn(),
    patch: vi.fn(),
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
    repository: { integrationId: "i1", fullName: "org/api-gateway", baseBranch: "main" },
    runStats: {
      recentSucceeded: 7,
      recentFailed: 2,
      lastRunStatus: "completed",
      lastRunAt: "2026-01-01T00:00:00Z",
    },
    updatedAt: "2026-01-01T00:00:00Z",
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
    repository: null,
    runStats: {
      recentSucceeded: 0,
      recentFailed: 0,
      lastRunStatus: null,
      lastRunAt: null,
    },
    updatedAt: "2026-01-01T00:00:00Z",
  },
];

function mockPipelinesList(pipelines: typeof mockPipelines) {
  mockList.mockImplementation(async (path: string) => {
    if (path === "/api/pipelines") {
      return { items: pipelines, total: pipelines.length, page: 1, limit: 20 };
    }
    return { items: [], total: 0, page: 1, limit: 100 };
  });
}

describe("PipelinesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRunParam = "";
  });

  it("shows loading skeleton initially", () => {
    mockList.mockReturnValue(new Promise(() => {})); // never resolves
    render(<PipelinesPage />);
    expect(document.querySelectorAll("[aria-hidden='true']").length).toBeGreaterThan(0);
  });

  it("renders the table columns", async () => {
    mockPipelinesList(mockPipelines);
    render(<PipelinesPage />);

    await waitFor(() => {
      expect(screen.getByText("Feature Dev Pipeline")).toBeInTheDocument();
    });

    expect(screen.getByText("Nome")).toBeInTheDocument();
    expect(screen.getByText("Repositório")).toBeInTheDocument();
    expect(screen.getByText("Últimos 10 runs")).toBeInTheDocument();
    expect(screen.getByText("Último run")).toBeInTheDocument();
    expect(screen.getByText("Atualizado")).toBeInTheDocument();
  });

  it("shows the run stats as ✓ 7 · ✗ 2", async () => {
    mockPipelinesList(mockPipelines);
    render(<PipelinesPage />);

    await waitFor(() => {
      expect(screen.getByText("Feature Dev Pipeline")).toBeInTheDocument();
    });

    expect(screen.getByText("✓ 7")).toBeInTheDocument();
    expect(screen.getByText("✗ 2")).toBeInTheDocument();
  });

  it("shows the repository name", async () => {
    mockPipelinesList(mockPipelines);
    render(<PipelinesPage />);

    await waitFor(() => {
      expect(screen.getByText("org/api-gateway")).toBeInTheDocument();
    });
  });

  it("shows 'Sem execuções' for a pipeline without runs", async () => {
    mockPipelinesList(mockPipelines);
    render(<PipelinesPage />);

    await waitFor(() => {
      expect(screen.getByText("QA Pipeline")).toBeInTheDocument();
    });

    // "Sem execuções" aparece na célula da linha e no <option> do filtro.
    expect(screen.getAllByText("Sem execuções").length).toBeGreaterThanOrEqual(1);
  });

  it("does not show the run status as the pipeline status", async () => {
    mockPipelinesList(mockPipelines);
    render(<PipelinesPage />);

    await waitFor(() => {
      expect(screen.getByText("Feature Dev Pipeline")).toBeInTheDocument();
    });

    // O status da pipeline (draft/running) não aparece como badge na tabela.
    expect(screen.queryByText("Rascunho")).not.toBeInTheDocument();
  });

  it("pre-selects the run filter from ?run=running in the URL", async () => {
    mockRunParam = "running";
    mockPipelinesList(mockPipelines);
    render(<PipelinesPage />);

    // O filtro é pré-selecionado na URL; a tabela filtra client-side.
    const filterSelect = await screen.findByLabelText("Último run");
    expect(filterSelect).toHaveValue("running");
  });

  it("search filters the table", async () => {
    mockPipelinesList(mockPipelines);
    render(<PipelinesPage />);

    await waitFor(() => {
      expect(screen.getByText("Feature Dev Pipeline")).toBeInTheDocument();
    });

    const search = screen.getByPlaceholderText("Buscar pipelines…");
    fireEvent.change(search, { target: { value: "QA" } });

    await waitFor(() => {
      expect(screen.queryByText("Feature Dev Pipeline")).not.toBeInTheDocument();
    });
    expect(screen.getByText("QA Pipeline")).toBeInTheDocument();
  });

  it("shows empty state when no pipelines", async () => {
    mockPipelinesList([]);
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

  it("navigates to pipeline detail on name link click", async () => {
    mockPipelinesList(mockPipelines);
    render(<PipelinesPage />);

    await waitFor(() => {
      expect(screen.getByText("Feature Dev Pipeline")).toBeInTheDocument();
    });

    const link = screen.getByRole("link", { name: "Feature Dev Pipeline" });
    expect(link).toHaveAttribute("href", "/pipelines/pipe-1");
  });

  it("row menu: Abrir navigates to the pipeline detail", async () => {
    mockPipelinesList(mockPipelines);
    render(<PipelinesPage />);
    await screen.findByText("Feature Dev Pipeline");

    // Uma linha por pipeline; a primeira é a pipe-1.
    const actionsButtons = screen.getAllByRole("button", { name: "Mais ações" });
    fireEvent.click(actionsButtons[0]);
    await waitFor(() => screen.getByRole("menuitem", { name: "Abrir" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Abrir" }));

    expect(mockPush).toHaveBeenCalledWith("/pipelines/pipe-1");
  });

  it("row menu: Monitor navigates to the run page", async () => {
    mockPipelinesList(mockPipelines);
    render(<PipelinesPage />);
    await screen.findByText("Feature Dev Pipeline");

    const actionsButtons = screen.getAllByRole("button", { name: "Mais ações" });
    fireEvent.click(actionsButtons[0]);
    await waitFor(() => screen.getByRole("menuitem", { name: "Monitor" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Monitor" }));

    expect(mockPush).toHaveBeenCalledWith("/pipelines/pipe-1/run");
  });
});
