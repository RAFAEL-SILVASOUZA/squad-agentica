import * as React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PipelinesPage from "./page";

// Mocks
const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

const mockAddToast = vi.fn();
vi.mock("@/components/ui/toast", () => ({
  useToast: () => ({ addToast: mockAddToast }),
}));

const mockList = vi.fn();
const mockPost = vi.fn();
const mockDelete = vi.fn();
// Preserva o ApiError real (mensagens traduzidas via CODE_MESSAGES) e só
// substitui as chamadas de rede por mocks — mesmo padrão de
// pipeline-header.test.tsx / repository-picker.test.tsx.
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
  },
];

/**
 * Mock path-aware de `api.list`: `/api/pipelines` responde a paginação de
 * pipelines; `/api/pipelines/{id}/runs` responde o(s) run(s) daquele
 * pipeline. Antes deste fix (review round 1, item 4), um `mockResolvedValue`
 * único respondia às duas rotas com o mesmo payload de pipelines.
 */
function mockPipelinesList(pipelines: typeof mockPipelines, runsByPipelineId: Record<string, unknown[]> = {}) {
  mockList.mockImplementation(async (path: string) => {
    if (path === "/api/pipelines") {
      return { items: pipelines, total: pipelines.length, page: 1, limit: 20 };
    }
    const match = /^\/api\/pipelines\/([^/]+)\/runs$/.exec(path);
    if (match) {
      const items = runsByPipelineId[match[1]] ?? [];
      return { items, total: items.length, page: 1, limit: 1 };
    }
    return { items: [], total: 0, page: 1, limit: 100 };
  });
}

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
    mockPipelinesList(mockPipelines);

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

  it("navigates to pipeline detail on card click", async () => {
    mockPipelinesList(mockPipelines);

    const user = userEvent.setup();
    render(<PipelinesPage />);

    await waitFor(() => {
      expect(screen.getByText("Feature Dev Pipeline")).toBeInTheDocument();
    });

    await user.click(screen.getByText("Feature Dev Pipeline"));
    expect(mockPush).toHaveBeenCalledWith("/pipelines/pipe-1");
  });

  it("shows running badge for running pipeline", async () => {
    mockPipelinesList(mockPipelines);

    render(<PipelinesPage />);

    await waitFor(() => {
      expect(screen.getByText("Executando")).toBeInTheDocument();
    });
  });

  it("shows the repository and the last-run status on the card", async () => {
    mockPipelinesList(mockPipelines, {
      "pipe-1": [
        {
          id: "run-1",
          pipelineId: "pipe-1",
          threadId: "t1",
          status: "completed",
          startedAt: "2026-01-01T00:00:00Z",
          completedAt: new Date(Date.now() - 5 * 60_000).toISOString(),
        },
      ],
    });

    render(<PipelinesPage />);

    await waitFor(() => {
      expect(screen.getByText("org/api-gateway (main)")).toBeInTheDocument();
    });
    expect(screen.getByText("Último run: Concluído há 5 min")).toBeInTheDocument();
    // pipe-2 has no runs seeded.
    expect(screen.getByText("Sem execuções")).toBeInTheDocument();
  });

  it("has a Monitor link to the run page for each card", async () => {
    mockPipelinesList(mockPipelines);

    render(<PipelinesPage />);

    expect(await screen.findByRole("link", { name: "Ver monitor de Feature Dev Pipeline" })).toHaveAttribute(
      "href",
      "/pipelines/pipe-1/run"
    );
  });

  it("menu: Duplicar calls POST duplicate and navigates to the new pipeline", async () => {
    mockPipelinesList(mockPipelines);
    mockPost.mockResolvedValue({ ...mockPipelines[0], id: "pipe-1-copy", name: "Feature Dev Pipeline (cópia)" });

    render(<PipelinesPage />);
    await screen.findByText("Feature Dev Pipeline");

    fireEvent.click(screen.getByRole("button", { name: "Mais ações de Feature Dev Pipeline" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Duplicar pipeline" }));

    await waitFor(() => expect(mockPost).toHaveBeenCalledWith("/api/pipelines/pipe-1/duplicate"));
    expect(mockPush).toHaveBeenCalledWith("/pipelines/pipe-1-copy");
  });

  it("menu: Excluir -> confirm -> DELETE removes the card from the list", async () => {
    let currentPipelines = mockPipelines;
    mockList.mockImplementation(async (path: string) => {
      if (path === "/api/pipelines") {
        return { items: currentPipelines, total: currentPipelines.length, page: 1, limit: 20 };
      }
      return { items: [], total: 0, page: 1, limit: 100 };
    });
    mockDelete.mockImplementation(async () => {
      currentPipelines = currentPipelines.filter((p) => p.id !== "pipe-1");
    });

    render(<PipelinesPage />);
    await screen.findByText("Feature Dev Pipeline");

    fireEvent.click(screen.getByRole("button", { name: "Mais ações de Feature Dev Pipeline" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Excluir pipeline" }));
    fireEvent.click(screen.getByRole("button", { name: "Excluir" }));

    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith("/api/pipelines/pipe-1"));
    await waitFor(() => expect(screen.queryByText("Feature Dev Pipeline")).not.toBeInTheDocument());
    expect(screen.getByText("QA Pipeline")).toBeInTheDocument();
    expect(mockAddToast).toHaveBeenCalledWith("success", "Pipeline excluído.");
  });

  it("menu: Excluir shows the translated error message on a 409 (graph_running)", async () => {
    const { ApiError } = await import("@/lib/api");
    mockPipelinesList(mockPipelines);
    mockDelete.mockRejectedValue(new ApiError(409, { error: "conflict", code: "graph_running" }));

    render(<PipelinesPage />);
    await screen.findByText("Feature Dev Pipeline");

    fireEvent.click(screen.getByRole("button", { name: "Mais ações de Feature Dev Pipeline" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Excluir pipeline" }));
    fireEvent.click(screen.getByRole("button", { name: "Excluir" }));

    await waitFor(() =>
      expect(mockAddToast).toHaveBeenCalledWith(
        "error",
        "O pipeline está em execução; aguarde ou pare o run antes de editar."
      )
    );
    expect(screen.getByText("Feature Dev Pipeline")).toBeInTheDocument();
  });
});
