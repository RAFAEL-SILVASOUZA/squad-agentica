import * as React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { ToolsEditor } from "./tools-editor";
import { ToastProvider } from "@/components/ui/toast";
import { ApiError } from "@/lib/api";

// ─── Mocks ───────────────────────────────────────────────────────────────────

const mockList = vi.fn();
const mockPost = vi.fn();
const mockPut = vi.fn();
const mockDelete = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    list: (...args: unknown[]) => mockList(...args),
    post: (...args: unknown[]) => mockPost(...args),
    put: (...args: unknown[]) => mockPut(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
    get: vi.fn(),
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

function makeTool(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "tool-1",
    name: "Calcular hash",
    description: "Calcula SHA256 de um texto",
    language: "python",
    script: "def main(inputs):\n    import hashlib\n    return {'hash': hashlib.sha256(inputs['data'].encode()).hexdigest()}",
    inputs: [{ name: "data", type: "string", required: true }],
    outputs: [{ name: "hash", type: "string", required: false }],
    status: "draft",
    created_at: "2026-09-26T10:00:00Z",
    updated_at: "2026-09-26T10:00:00Z",
    ...overrides,
  };
}

function renderEditor() {
  return render(
    <ToastProvider>
      <ToolsEditor />
    </ToastProvider>
  );
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("ToolsEditor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockList.mockResolvedValue({ items: [], total: 0, page: 1, limit: 100 });
  });

  it("renders loading skeletons on initial load", () => {
    mockList.mockReturnValue(new Promise(() => {}));
    renderEditor();
    expect(screen.queryByText("Nenhuma tool ainda")).not.toBeInTheDocument();
  });

  it("renders empty state with CTA when no tools", async () => {
    renderEditor();
    await waitFor(() => {
      expect(screen.getByText("Nenhuma tool ainda")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /criar primeira tool/i })).toBeInTheDocument();
  });

  it("renders tool cards with name, status and description", async () => {
    mockList.mockResolvedValue({
      items: [makeTool()],
      total: 1,
      page: 1,
      limit: 100,
    });
    renderEditor();
    await waitFor(() => {
      expect(screen.getByText("Calcular hash")).toBeInTheDocument();
    });
    expect(screen.getByText("Calcula SHA256 de um texto")).toBeInTheDocument();
    expect(screen.getByText("Rascunho")).toBeInTheDocument();
  });

  it("opens create modal when CTA is clicked", async () => {
    renderEditor();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /criar primeira tool/i })).toBeInTheDocument();
    });
    const btn = screen.getByRole("button", { name: /criar primeira tool/i });
    fireEvent.click(btn);
    await waitFor(() => {
      expect(document.body.querySelector("[role='dialog']")).not.toBeNull();
    });
  });

  it("submits create with script and I/O", async () => {
    mockPost.mockResolvedValue(makeTool({ id: "tool-new" }));
    mockList.mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 100 });
    renderEditor();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /criar primeira tool/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /criar primeira tool/i }));
    await waitFor(() => {
      expect(document.body.querySelector("[role='dialog']")).not.toBeNull();
    });

    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Tool nova" } });
    fireEvent.change(screen.getByLabelText("Script"), { target: { value: "def main(inputs):\n    pass" } });

    fireEvent.click(screen.getByRole("button", { name: /criar tool/i }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/tools", {
        name: "Tool nova",
        description: "",
        language: "python",
        script: "def main(inputs):\n    pass",
        inputs: [],
        outputs: [],
      });
    });
  });

  it("shows form error when script is empty", async () => {
    renderEditor();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /criar primeira tool/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /criar primeira tool/i }));
    await waitFor(() => {
      expect(document.body.querySelector("[role='dialog']")).not.toBeNull();
    });

    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Sem script" } });
    fireEvent.click(screen.getByRole("button", { name: /criar tool/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/script é obrigatório/i);
    });
    expect(mockPost).not.toHaveBeenCalled();
  });

  it("opens edit modal prefilled when Editar is clicked", async () => {
    mockList.mockResolvedValue({ items: [makeTool()], total: 1, page: 1, limit: 100 });
    renderEditor();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /editar tool calcular hash/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /editar tool calcular hash/i }));

    await waitFor(() => {
      expect(document.body.querySelector("[role='dialog']")).not.toBeNull();
    });
    expect((screen.getByLabelText("Nome") as HTMLInputElement).value).toBe("Calcular hash");
  });

  it("submits update via PUT when saving an edit", async () => {
    mockList.mockResolvedValue({ items: [makeTool()], total: 1, page: 1, limit: 100 });
    mockPut.mockResolvedValue(makeTool({ name: "Renomeada" }));
    renderEditor();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /editar tool calcular hash/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /editar tool calcular hash/i }));

    await waitFor(() => {
      expect(document.body.querySelector("[role='dialog']")).not.toBeNull();
    });
    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Renomeada" } });
    fireEvent.click(screen.getByRole("button", { name: /salvar alterações/i }));

    await waitFor(() => {
      expect(mockPut).toHaveBeenCalledWith("/api/tools/tool-1", expect.objectContaining({
        name: "Renomeada",
      }));
    });
  });

  it("deploys a tool via POST deploy", async () => {
    mockList.mockResolvedValue({ items: [makeTool()], total: 1, page: 1, limit: 100 });
    mockPost.mockResolvedValue(undefined);
    renderEditor();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /deploy tool calcular hash/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /deploy tool calcular hash/i }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/tools/tool-1/deploy");
    });
  });

  it("tests a tool with input and shows result", async () => {
    mockList.mockResolvedValue({ items: [makeTool()], total: 1, page: 1, limit: 100 });
    mockPost.mockResolvedValue({ success: true, output: '{"hash": "abc123"}', duration_ms: 42 });
    renderEditor();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /testar tool calcular hash/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /testar tool calcular hash/i }));

    await waitFor(() => {
      expect(document.body.querySelector("[role='dialog']")).not.toBeNull();
    });
    fireEvent.change(screen.getByLabelText("Input de exemplo (JSON)"), {
      target: { value: '{"data": "teste"}' },
    });
    fireEvent.click(screen.getByRole("button", { name: /executar teste/i }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/tools/tool-1/test", { args: { data: "teste" } });
    });
    await waitFor(() => {
      expect(screen.getByText("Sucesso")).toBeInTheDocument();
    });
  });

  it("teaches the execute(**kwargs) signature the sandbox calls (E7)", async () => {
    renderEditor();
    fireEvent.click(await screen.findByRole("button", { name: /criar primeira tool/i }));
    const script = await screen.findByLabelText("Script");
    expect(script.getAttribute("placeholder")).toContain("def execute(**kwargs)");
  });

  it("shows the sandbox error message instead of a bare Erro (E7)", async () => {
    mockList.mockResolvedValue({ items: [makeTool()], total: 1, page: 1, limit: 100 });
    mockPost.mockResolvedValue({
      result: { error: "module has no attribute 'execute'", traceback: "Traceback ..." },
    });
    renderEditor();
    fireEvent.click(await screen.findByRole("button", { name: /testar tool calcular hash/i }));
    fireEvent.click(await screen.findByRole("button", { name: /executar teste/i }));
    expect(await screen.findByText(/module has no attribute 'execute'/)).toBeInTheDocument();
  });

  it("asks confirmation and deletes a tool", async () => {
    mockList.mockResolvedValue({ items: [makeTool()], total: 1, page: 1, limit: 100 });
    mockDelete.mockResolvedValue(undefined);
    renderEditor();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /excluir tool calcular hash/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /excluir tool calcular hash/i }));

    await waitFor(() => {
      expect(document.body.querySelector("[role='dialog']")).not.toBeNull();
    });
    fireEvent.click(screen.getByRole("button", { name: /^excluir$/i }));

    await waitFor(() => {
      expect(mockDelete).toHaveBeenCalledWith("/api/tools/tool-1");
    });
  });

  it("shows error state with retry on fetch failure", async () => {
    mockList.mockRejectedValue(new Error("network down"));
    renderEditor();
    await waitFor(() => {
      expect(screen.getByText("network down")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /tentar novamente/i })).toBeInTheDocument();
  });

  it("refetches on retry", async () => {
    mockList.mockRejectedValueOnce(new Error("boom"));
    mockList.mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 100 });
    renderEditor();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /tentar novamente/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /tentar novamente/i }));
    await waitFor(() => {
      expect(mockList).toHaveBeenCalledTimes(2);
    });
  });

  it("shows API error details on save failure", async () => {
    renderEditor();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /criar primeira tool/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /criar primeira tool/i }));
    await waitFor(() => {
      expect(document.body.querySelector("[role='dialog']")).not.toBeNull();
    });

    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "X" } });
    fireEvent.change(screen.getByLabelText("Script"), { target: { value: "y" } });

    mockPost.mockRejectedValue(
      new ApiError(400, { error: "validation", code: "invalid", details: { errors: ["nome curto"] } })
    );
    fireEvent.click(screen.getByRole("button", { name: /criar tool/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/nome curto/);
    });
  });
});
