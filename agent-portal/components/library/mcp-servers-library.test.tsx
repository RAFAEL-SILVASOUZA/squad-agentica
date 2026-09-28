import * as React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MCPServersLibrary } from "./mcp-servers-library";
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

function makeServer(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "mcp-1",
    name: "Servidor de busca",
    description: "Busca na web",
    transport: "stdio",
    command: "npx @modelcontextprotocol/server-fetch",
    url: undefined,
    env: {},
    status: "disconnected",
    discoveredTools: [],
    created_at: "2026-09-26T10:00:00Z",
    updated_at: "2026-09-26T10:00:00Z",
    ...overrides,
  };
}

function renderLibrary() {
  return render(
    <ToastProvider>
      <MCPServersLibrary />
    </ToastProvider>
  );
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("MCPServersLibrary", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockList.mockResolvedValue({ items: [], total: 0, page: 1, limit: 100 });
  });

  it("renders loading skeletons on initial load", () => {
    mockList.mockReturnValue(new Promise(() => {}));
    renderLibrary();
    expect(screen.queryByText("Nenhum servidor MCP ainda")).not.toBeInTheDocument();
  });

  it("renders empty state with CTA when no servers", async () => {
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByText("Nenhum servidor MCP ainda")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /registrar primeiro servidor/i })).toBeInTheDocument();
  });

  it("renders server cards with name, status and description", async () => {
    mockList.mockResolvedValue({
      items: [makeServer()],
      total: 1,
      page: 1,
      limit: 100,
    });
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByText("Servidor de busca")).toBeInTheDocument();
    });
    expect(screen.getByText("Busca na web")).toBeInTheDocument();
    expect(screen.getByText("Desconectado")).toBeInTheDocument();
  });

  it("opens create modal when CTA is clicked", async () => {
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /registrar primeiro servidor/i })).toBeInTheDocument();
    });
    const btn = screen.getByRole("button", { name: /registrar primeiro servidor/i });
    fireEvent.click(btn);
    await waitFor(() => {
      expect(document.body.querySelector("[role='dialog']")).not.toBeNull();
    });
  });

  it("submits create with stdio transport and command", async () => {
    mockPost.mockResolvedValue(makeServer({ id: "mcp-new" }));
    mockList.mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 100 });
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /registrar primeiro servidor/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /registrar primeiro servidor/i }));
    await waitFor(() => {
      expect(document.body.querySelector("[role='dialog']")).not.toBeNull();
    });

    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Servidor novo" } });
    fireEvent.change(screen.getByLabelText("Comando"), { target: { value: "npx server" } });

    fireEvent.click(screen.getByRole("button", { name: /registrar servidor/i }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/mcp-servers", {
        name: "Servidor novo",
        description: "",
        transport: "stdio",
        command: "npx server",
        env: {},
      });
    });
  });

  it("shows form error when command is empty for stdio", async () => {
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /registrar primeiro servidor/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /registrar primeiro servidor/i }));
    await waitFor(() => {
      expect(document.body.querySelector("[role='dialog']")).not.toBeNull();
    });

    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Sem comando" } });
    fireEvent.click(screen.getByRole("button", { name: /registrar servidor/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/comando é obrigatório/i);
    });
    expect(mockPost).not.toHaveBeenCalled();
  });

  it("opens edit modal prefilled when Editar is clicked", async () => {
    mockList.mockResolvedValue({ items: [makeServer()], total: 1, page: 1, limit: 100 });
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /editar servidor servidor de busca/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /editar servidor servidor de busca/i }));

    await waitFor(() => {
      expect(document.body.querySelector("[role='dialog']")).not.toBeNull();
    });
    expect((screen.getByLabelText("Nome") as HTMLInputElement).value).toBe("Servidor de busca");
  });

  it("submits update via PUT when saving an edit", async () => {
    mockList.mockResolvedValue({ items: [makeServer()], total: 1, page: 1, limit: 100 });
    mockPut.mockResolvedValue(makeServer({ name: "Renomeado" }));
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /editar servidor servidor de busca/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /editar servidor servidor de busca/i }));

    await waitFor(() => {
      expect(document.body.querySelector("[role='dialog']")).not.toBeNull();
    });
    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Renomeado" } });
    fireEvent.click(screen.getByRole("button", { name: /salvar alterações/i }));

    await waitFor(() => {
      expect(mockPut).toHaveBeenCalledWith("/api/mcp-servers/mcp-1", expect.objectContaining({
        name: "Renomeado",
      }));
    });
  });

  it("tests connection and shows discovered tools", async () => {
    mockList.mockResolvedValue({ items: [makeServer()], total: 1, page: 1, limit: 100 });
    // Formato do contrato (POST /api/mcp-servers/:id/test).
    mockPost.mockResolvedValue({ status: "connected", discoveredTools: [{ name: "search" }, { name: "fetch" }] });
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /testar conexão servidor de busca/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /testar conexão servidor de busca/i }));

    await waitFor(() => {
      expect(document.body.querySelector("[role='dialog']")).not.toBeNull();
    });
    const testBtn = screen.getAllByRole("button", { name: /testar conexão/i }).pop();
    if (testBtn) fireEvent.click(testBtn);

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/mcp-servers/mcp-1/test");
    });
    await waitFor(() => {
      expect(screen.getByText("Conectado")).toBeInTheDocument();
    });
    expect(screen.getAllByText(/tools descobertas/i).length).toBeGreaterThan(0);
  });

  it("shows the failure reason returned by the test endpoint", async () => {
    mockList.mockResolvedValue({ items: [makeServer()], total: 1, page: 1, limit: 100 });
    mockPost.mockResolvedValue({
      status: "error",
      discoveredTools: [],
      error: "Não foi possível conectar a http://x/sse: timeout",
    });
    renderLibrary();
    fireEvent.click(await screen.findByRole("button", { name: /testar conexão servidor de busca/i }));
    const testBtn = (await screen.findAllByRole("button", { name: /testar conexão/i })).pop();
    if (testBtn) fireEvent.click(testBtn);
    expect(await screen.findByText("Falha na conexão")).toBeInTheDocument();
    expect(screen.getByText(/Não foi possível conectar a http:\/\/x\/sse/)).toBeInTheDocument();
  });

  it("asks confirmation and deletes a server", async () => {
    mockList.mockResolvedValue({ items: [makeServer()], total: 1, page: 1, limit: 100 });
    mockDelete.mockResolvedValue(undefined);
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /excluir servidor servidor de busca/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /excluir servidor servidor de busca/i }));

    await waitFor(() => {
      expect(document.body.querySelector("[role='dialog']")).not.toBeNull();
    });
    fireEvent.click(screen.getByRole("button", { name: /^excluir$/i }));

    await waitFor(() => {
      expect(mockDelete).toHaveBeenCalledWith("/api/mcp-servers/mcp-1");
    });
  });

  it("shows error state with retry on fetch failure", async () => {
    mockList.mockRejectedValue(new Error("network down"));
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByText("network down")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /tentar novamente/i })).toBeInTheDocument();
  });

  it("refetches on retry", async () => {
    mockList.mockRejectedValueOnce(new Error("boom"));
    mockList.mockResolvedValueOnce({ items: [], total: 0, page: 1, limit: 100 });
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /tentar novamente/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /tentar novamente/i }));
    await waitFor(() => {
      expect(mockList).toHaveBeenCalledTimes(2);
    });
  });

  it("shows API error details on save failure", async () => {
    renderLibrary();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /registrar primeiro servidor/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /registrar primeiro servidor/i }));
    await waitFor(() => {
      expect(document.body.querySelector("[role='dialog']")).not.toBeNull();
    });

    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "X" } });
    fireEvent.change(screen.getByLabelText("Comando"), { target: { value: "y" } });

    mockPost.mockRejectedValue(
      new ApiError(400, { error: "validation", code: "invalid", details: { errors: ["nome curto"] } })
    );
    fireEvent.click(screen.getByRole("button", { name: /registrar servidor/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/nome curto/);
    });
  });
});
