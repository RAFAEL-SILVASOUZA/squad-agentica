import * as React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { KnowledgeView } from "./knowledge-view";
import { ToastProvider } from "@/components/ui/toast";
import { ApiError } from "@/lib/api";

// ─── Mocks ───────────────────────────────────────────────────────────────────

const mockList = vi.fn();
const mockPost = vi.fn();
const mockGet = vi.fn();
const mockDelete = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    list: (...args: unknown[]) => mockList(...args),
    post: (...args: unknown[]) => mockPost(...args),
    get: (...args: unknown[]) => mockGet(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
    put: vi.fn(),
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

// ─── Test data ───────────────────────────────────────────────────────────────

function makeBase(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "kb-1",
    name: "Base de documentação",
    description: "Documentação do produto",
    scope: "global",
    documentCount: 2,
    created_at: "2026-09-26T10:00:00Z",
    updated_at: "2026-09-26T10:00:00Z",
    ...overrides,
  };
}

function makeDoc(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "doc-1",
    name: "manual.pdf",
    status: "ready",
    size_bytes: 1024,
    uploaded_at: "2026-09-26T10:00:00Z",
    ...overrides,
  };
}

function renderView() {
  return render(
    <ToastProvider>
      <KnowledgeView />
    </ToastProvider>
  );
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("KnowledgeView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockList.mockResolvedValue({ items: [], total: 0, page: 1, limit: 100 });
    mockGet.mockResolvedValue({ items: [] });
  });

  it("renders loading skeletons on initial load", () => {
    mockList.mockReturnValue(new Promise(() => {}));
    renderView();
    expect(screen.queryByText("Nenhuma base ainda")).not.toBeInTheDocument();
  });

  it("renders empty state with CTA when no bases", async () => {
    renderView();
    await waitFor(() => {
      expect(screen.getByText("Nenhuma base ainda")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /nova base/i })).toBeInTheDocument();
  });

  it("renders base cards in sidebar", async () => {
    mockList.mockResolvedValue({
      items: [makeBase()],
      total: 1,
      page: 1,
      limit: 100,
    });
    renderView();
    await waitFor(() => {
      expect(screen.getByText("Base de documentação")).toBeInTheDocument();
    });
    expect(screen.getByText("2 documentos")).toBeInTheDocument();
  });

  it("opens create modal when Nova base is clicked", async () => {
    renderView();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /nova base/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /nova base/i }));
    await waitFor(() => {
      expect(document.body.querySelector("[role='dialog']")).not.toBeNull();
    });
  });

  it("submits create with name and scope", async () => {
    mockPost.mockResolvedValue(makeBase({ id: "kb-new" }));
    mockList.mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 100 });
    renderView();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /nova base/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /nova base/i }));
    await waitFor(() => {
      expect(document.body.querySelector("[role='dialog']")).not.toBeNull();
    });

    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Base nova" } });
    fireEvent.click(screen.getByRole("button", { name: /criar base/i }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/knowledge", {
        name: "Base nova",
        description: "",
        scope: "global",
        source: "upload",
        similarityThreshold: 0.7,
        topK: 5,
      });
    });
  });

  it("shows form error when name is empty", async () => {
    renderView();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /nova base/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /nova base/i }));
    await waitFor(() => {
      expect(document.body.querySelector("[role='dialog']")).not.toBeNull();
    });

    fireEvent.click(screen.getByRole("button", { name: /criar base/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/nome é obrigatório/i);
    });
    expect(mockPost).not.toHaveBeenCalled();
  });

  it("selects a base and loads documents", async () => {
    mockList.mockResolvedValue({ items: [makeBase()], total: 1, page: 1, limit: 100 });
    mockList.mockImplementation(async (path: string) => ({
      items: path.endsWith("/documents") ? [makeDoc(), makeDoc({ id: "doc-2", name: "api.pdf" })] : [makeBase()],
      total: path.endsWith("/documents") ? 2 : 1, page: 1, limit: 100,
    }));
    renderView();
    await waitFor(() => {
      expect(screen.getByText("Base de documentação")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("Base de documentação"));

    await waitFor(() => {
      expect(mockList).toHaveBeenCalledWith("/api/knowledge/kb-1/documents", { page: 1, limit: 100 });
    });
    await waitFor(() => {
      expect(screen.getByText("manual.pdf")).toBeInTheDocument();
    });
  });

  it("uploads a document", async () => {
    mockList.mockResolvedValue({ items: [makeBase()], total: 1, page: 1, limit: 100 });
    mockGet.mockResolvedValue({ items: [] });
    mockPost.mockResolvedValue(undefined);
    renderView();
    await waitFor(() => {
      expect(screen.getByText("Base de documentação")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("Base de documentação"));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /selecionar arquivo/i })).toBeInTheDocument();
    });

    const fileInput = document.getElementById("knowledge-upload") as HTMLInputElement;
    const file = new File(["content"], "test.pdf", { type: "application/pdf" });
    fireEvent.change(fileInput, { target: { files: [file] } });

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        "/api/knowledge/kb-1/upload",
        expect.any(FormData)
      );
    });
  });

  it("não mostra mais a consulta de teste e exibe o chat da base", async () => {
    mockList.mockResolvedValue({ items: [makeBase()], total: 1, page: 1, limit: 100 });
    renderView();
    fireEvent.click(await screen.findByText("Base de documentação"));
    expect(await screen.findByLabelText("Mensagem")).toBeInTheDocument();
    expect(document.getElementById("knowledge-query")).toBeNull();
    expect(screen.queryByText("Consulta de teste")).not.toBeInTheDocument();
  });

  it("increments the base document count after an upload", async () => {
    mockList.mockImplementation(async (path: string) =>
      path.endsWith("/documents")
        ? { items: [{ id: "d1", name: "a.md", status: "ready", size: 1, chunkCount: 1, createdAt: "" }], total: 1, page: 1, limit: 100 }
        : { items: [makeBase({ documentCount: 0 })], total: 1, page: 1, limit: 100 }
    );
    mockPost.mockResolvedValue(undefined);
    renderView();
    fireEvent.click(await screen.findByText("Base de documentação"));
    const fileInput = document.getElementById("knowledge-upload") as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [new File(["x"], "a.md")] } });
    expect(await screen.findByText("1 documentos")).toBeInTheDocument();
  });

  it("asks confirmation and deletes a base", async () => {
    mockList.mockResolvedValue({ items: [makeBase()], total: 1, page: 1, limit: 100 });
    mockGet.mockResolvedValue({ items: [] });
    mockDelete.mockResolvedValue(undefined);
    renderView();
    await waitFor(() => {
      expect(screen.getByText("Base de documentação")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("Base de documentação"));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /excluir base/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /excluir base/i }));

    await waitFor(() => {
      expect(document.body.querySelector("[role='dialog']")).not.toBeNull();
    });
    const deleteBtns = screen.getAllByRole("button", { name: /^excluir$/i });
    const confirmDeleteBtn = deleteBtns.pop();
    if (confirmDeleteBtn) fireEvent.click(confirmDeleteBtn);

    await waitFor(() => {
      expect(mockDelete).toHaveBeenCalledWith("/api/knowledge/kb-1");
    });
  });

  it("shows error state with retry on fetch failure", async () => {
    mockList.mockRejectedValue(new Error("network down"));
    renderView();
    await waitFor(() => {
      expect(screen.getByText("network down")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /tentar novamente/i })).toBeInTheDocument();
  });

  it("refetches on retry", async () => {
    mockList.mockRejectedValueOnce(new Error("boom"));
    mockList.mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 100 });
    renderView();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /tentar novamente/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /tentar novamente/i }));
    await waitFor(() => {
      expect(mockList).toHaveBeenCalledTimes(2);
    });
  });

  it("shows API error details on create failure", async () => {
    renderView();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /nova base/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /nova base/i }));
    await waitFor(() => {
      expect(document.body.querySelector("[role='dialog']")).not.toBeNull();
    });

    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "X" } });

    mockPost.mockRejectedValue(
      new ApiError(400, { error: "validation", code: "invalid", details: { errors: ["nome curto"] } })
    );
    fireEvent.click(screen.getByRole("button", { name: /criar base/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/nome curto/);
    });
  });
});
