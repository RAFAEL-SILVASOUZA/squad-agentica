import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { RepositoryPicker } from "./repository-picker";
import { ApiError } from "@/lib/api";

const mocks = vi.hoisted(() => ({ list: vi.fn(), get: vi.fn() }));
vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  api: { list: mocks.list, get: mocks.get, post: vi.fn(), put: vi.fn(), delete: vi.fn(), patch: vi.fn() },
}));
const mockList = mocks.list;
const mockGet = mocks.get;

beforeEach(() => {
  vi.clearAllMocks();
});

describe("RepositoryPicker", () => {
  it("loads repositories of the chosen connection and preselects the default branch", async () => {
    mockList.mockResolvedValue({ items: [{ id: "i1", type: "github", name: "GH", config: {} }], total: 1, page: 1, limit: 100 });
    mockGet.mockImplementation(async (path: string) =>
      path.endsWith("/repositories") ? { items: [{ fullName: "o/r", defaultBranch: "develop" }] }
        : { items: ["develop", "main"] });
    const onChange = vi.fn();
    render(<RepositoryPicker value={null} onChange={onChange} />);
    fireEvent.change(await screen.findByLabelText("Conexão"), { target: { value: "i1" } });
    // Selecionar a conexão é um estado intermediário: nada é notificado ainda
    // (review round 1, item crítico 1).
    await screen.findByLabelText("Repositório");
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Repositório"), { target: { value: "o/r" } });
    await waitFor(() => expect(onChange).toHaveBeenLastCalledWith({ integrationId: "i1", fullName: "o/r", baseBranch: "develop" }));
  });

  it("filters the repository list by search text (case-insensitive, spec §4)", async () => {
    mockList.mockResolvedValue({ items: [{ id: "i1", type: "github", name: "GH", config: {} }], total: 1, page: 1, limit: 100 });
    mockGet.mockImplementation(async (path: string) =>
      path.endsWith("/repositories")
        ? { items: [{ fullName: "org/api-gateway", defaultBranch: "main" }, { fullName: "org/web-portal", defaultBranch: "main" }] }
        : { items: ["main"] });
    render(<RepositoryPicker value={null} onChange={vi.fn()} />);
    fireEvent.change(await screen.findByLabelText("Conexão"), { target: { value: "i1" } });
    const repoSelect = await screen.findByLabelText("Repositório");
    expect(repoSelect.querySelectorAll("option")).toHaveLength(3); // placeholder + 2 repos
    fireEvent.change(screen.getByLabelText("Buscar repositório"), { target: { value: "WEB" } });
    await waitFor(() => expect(screen.getByLabelText("Repositório").querySelectorAll("option")).toHaveLength(2)); // placeholder + 1 repo
    expect(screen.getByRole("option", { name: "org/web-portal" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "org/api-gateway" })).not.toBeInTheDocument();
  });

  it("shows a link to Integrations when there is no Git connection", async () => {
    mockList.mockResolvedValue({ items: [], total: 0, page: 1, limit: 100 });
    render(<RepositoryPicker value={null} onChange={vi.fn()} />);
    expect(await screen.findByRole("link", { name: /Cadastrar conexão Git/i })).toHaveAttribute("href", "/integrations");
  });

  it("preselects the existing value's connection and repository", async () => {
    mockList.mockResolvedValue({ items: [{ id: "i1", type: "github", name: "GH", config: {} }, { id: "i2", type: "azure", name: "AZ", config: {} }], total: 2, page: 1, limit: 100 });
    mockGet.mockImplementation(async (path: string) =>
      path.endsWith("/repositories") ? { items: [{ fullName: "o/r", defaultBranch: "main" }] }
        : { items: ["main"] });
    render(<RepositoryPicker value={{ integrationId: "i1", fullName: "o/r", baseBranch: "main" }} onChange={vi.fn()} />);
    expect(await screen.findByLabelText("Conexão")).toHaveValue("i1");
    expect(await screen.findByLabelText("Repositório")).toHaveValue("o/r");
    expect(await screen.findByLabelText("Branch")).toHaveValue("main");
  });

  it("clears the value with 'Sem repositório'", async () => {
    mockList.mockResolvedValue({ items: [{ id: "i1", type: "github", name: "GH", config: {} }], total: 1, page: 1, limit: 100 });
    mockGet.mockImplementation(async (path: string) =>
      path.endsWith("/repositories") ? { items: [{ fullName: "o/r", defaultBranch: "main" }] }
        : { items: ["main"] });
    const onChange = vi.fn();
    render(<RepositoryPicker value={{ integrationId: "i1", fullName: "o/r", baseBranch: "main" }} onChange={onChange} />);
    await screen.findByLabelText("Repositório");
    fireEvent.click(screen.getByRole("button", { name: "Sem repositório" }));
    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it("shows the translated error message when loading connections fails", async () => {
    mockList.mockRejectedValue(new ApiError(500, { error: "internal error", code: "internal_error" }));
    render(<RepositoryPicker value={null} onChange={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Erro interno do servidor. Tente novamente.");
  });
});
