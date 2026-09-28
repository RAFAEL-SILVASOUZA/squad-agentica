import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { PipelineHeader } from "./pipeline-header";
import { ToastProvider } from "@/components/ui/toast";
import { ApiError } from "@/lib/api";
import type { Pipeline } from "@/lib/types";

const mocks = vi.hoisted(() => ({ list: vi.fn(), get: vi.fn(), post: vi.fn(), delete: vi.fn() }));
vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  api: { list: mocks.list, get: mocks.get, post: mocks.post, put: vi.fn(), delete: mocks.delete, patch: vi.fn() },
}));
const mockList = mocks.list;
const mockGet = mocks.get;
const mockPost = mocks.post;
const mockDelete = mocks.delete;

function makePipeline(overrides: Partial<Pipeline> = {}): Pipeline {
  return {
    id: "p1",
    ownerId: "u1",
    name: "Novo pipeline",
    description: "",
    status: "draft",
    entryNodeId: "",
    nodes: [],
    edges: [],
    currentCheckpoint: null,
    startedAt: null,
    completedAt: null,
    repository: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockList.mockResolvedValue({ items: [], total: 0, page: 1, limit: 100 });
});

describe("PipelineHeader", () => {
  it("edits the name inline and saves on Enter", async () => {
    const onChange = vi.fn();
    render(
      <ToastProvider>
        <PipelineHeader pipeline={makePipeline({ name: "Novo pipeline" })} onChange={onChange} onDeleted={vi.fn()} onDuplicated={vi.fn()} autoEditName />
      </ToastProvider>
    );
    const input = screen.getByLabelText("Nome do pipeline");
    fireEvent.change(input, { target: { value: "Gerador de API" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith({ name: "Gerador de API" });
  });

  it("refuses an empty name", () => {
    const onChange = vi.fn();
    render(
      <ToastProvider>
        <PipelineHeader pipeline={makePipeline()} onChange={onChange} onDeleted={vi.fn()} onDuplicated={vi.fn()} autoEditName />
      </ToastProvider>
    );
    const input = screen.getByLabelText("Nome do pipeline");
    fireEvent.change(input, { target: { value: "   " } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Informe um nome");
  });

  it("cancels the name edit on Escape without calling onChange", () => {
    const onChange = vi.fn();
    render(
      <ToastProvider>
        <PipelineHeader pipeline={makePipeline({ name: "Original" })} onChange={onChange} onDeleted={vi.fn()} onDuplicated={vi.fn()} autoEditName />
      </ToastProvider>
    );
    const input = screen.getByLabelText("Nome do pipeline");
    fireEvent.change(input, { target: { value: "Mudou" } });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "Original" })).toBeInTheDocument();
  });

  it("shows the name as a heading when not editing, clicking it starts editing", () => {
    render(
      <ToastProvider>
        <PipelineHeader pipeline={makePipeline({ name: "Meu pipeline" })} onChange={vi.fn()} onDeleted={vi.fn()} onDuplicated={vi.fn()} />
      </ToastProvider>
    );
    expect(screen.getByRole("heading", { name: "Meu pipeline" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("heading", { name: "Meu pipeline" }));
    expect(screen.getByLabelText("Nome do pipeline")).toBeInTheDocument();
  });

  it("edits the description and saves on blur", () => {
    const onChange = vi.fn();
    render(
      <ToastProvider>
        <PipelineHeader pipeline={makePipeline({ description: "Antiga" })} onChange={onChange} onDeleted={vi.fn()} onDuplicated={vi.fn()} />
      </ToastProvider>
    );
    fireEvent.click(screen.getByText("Antiga"));
    const textarea = screen.getByLabelText("Descrição do pipeline");
    fireEvent.change(textarea, { target: { value: "Nova descrição" } });
    fireEvent.blur(textarea);
    expect(onChange).toHaveBeenCalledWith({ description: "Nova descrição" });
  });

  it("shows the repository chip and clears it via the popover", async () => {
    mockList.mockResolvedValue({ items: [{ id: "i1", type: "github", name: "GH", config: {} }], total: 1, page: 1, limit: 100 });
    mockGet.mockImplementation(async (path: string) =>
      path.endsWith("/repositories") ? { items: [{ fullName: "o/r", defaultBranch: "develop" }] } : { items: ["develop"] }
    );
    const onChange = vi.fn();
    render(
      <ToastProvider>
        <PipelineHeader
          pipeline={makePipeline({ repository: { integrationId: "i1", fullName: "o/r", baseBranch: "develop" } })}
          onChange={onChange}
          onDeleted={vi.fn()}
          onDuplicated={vi.fn()}
        />
      </ToastProvider>
    );
    const chip = screen.getByRole("button", { name: "Repositório: o/r (develop)" });
    fireEvent.click(chip);
    fireEvent.click(await screen.findByRole("button", { name: "Sem repositório" }));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith({ repository: null }));
  });

  it("attaches a repository from scratch: connection alone does not save, repository does, branch updates it (review round 1, item crítico 1)", async () => {
    mockList.mockResolvedValue({ items: [{ id: "i1", type: "github", name: "GH", config: {} }], total: 1, page: 1, limit: 100 });
    mockGet.mockImplementation(async (path: string) =>
      path.endsWith("/repositories") ? { items: [{ fullName: "o/r", defaultBranch: "develop" }] } : { items: ["develop", "main"] }
    );
    const onChange = vi.fn();
    render(
      <ToastProvider>
        <PipelineHeader pipeline={makePipeline({ repository: null })} onChange={onChange} onDeleted={vi.fn()} onDuplicated={vi.fn()} />
      </ToastProvider>
    );
    // Abre o popover (chip "Sem repositório").
    fireEvent.click(screen.getByRole("button", { name: "Sem repositório" }));
    const dialog = screen.getByRole("dialog", { name: "Repositório do pipeline" });

    // Escolher apenas a conexão é um estado intermediário: nada é salvo e o popover continua aberto.
    fireEvent.change(await screen.findByLabelText("Conexão"), { target: { value: "i1" } });
    await screen.findByLabelText("Repositório");
    expect(onChange).not.toHaveBeenCalled();
    expect(dialog).toBeInTheDocument();

    // Escolher o repositório é uma escolha completa: salva com a branch padrão.
    fireEvent.change(screen.getByLabelText("Repositório"), { target: { value: "o/r" } });
    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith({ repository: { integrationId: "i1", fullName: "o/r", baseBranch: "develop" } })
    );
    expect(dialog).toBeInTheDocument();

    // Trocar a branch atualiza o valor salvo.
    fireEvent.change(await screen.findByLabelText("Branch"), { target: { value: "main" } });
    await waitFor(() =>
      expect(onChange).toHaveBeenLastCalledWith({ repository: { integrationId: "i1", fullName: "o/r", baseBranch: "main" } })
    );
  });

  it("shows 'Sem repositório' as the chip label when there is none", () => {
    render(
      <ToastProvider>
        <PipelineHeader pipeline={makePipeline({ repository: null })} onChange={vi.fn()} onDeleted={vi.fn()} onDuplicated={vi.fn()} />
      </ToastProvider>
    );
    expect(screen.getByRole("button", { name: "Sem repositório" })).toBeInTheDocument();
  });

  it("duplicates the pipeline from the 'Mais ações' menu", async () => {
    mockPost.mockResolvedValue(makePipeline({ id: "p2", name: "X (cópia)" }));
    const onDuplicated = vi.fn();
    render(
      <ToastProvider>
        <PipelineHeader pipeline={makePipeline({ id: "p1" })} onChange={vi.fn()} onDeleted={vi.fn()} onDuplicated={onDuplicated} />
      </ToastProvider>
    );
    fireEvent.click(screen.getByRole("button", { name: "Mais ações" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Duplicar pipeline" }));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith("/api/pipelines/p1/duplicate"));
    expect(onDuplicated).toHaveBeenCalledWith("p2");
  });

  it("closes the 'Mais ações' menu on Escape", () => {
    render(
      <ToastProvider>
        <PipelineHeader pipeline={makePipeline()} onChange={vi.fn()} onDeleted={vi.fn()} onDuplicated={vi.fn()} />
      </ToastProvider>
    );
    fireEvent.click(screen.getByRole("button", { name: "Mais ações" }));
    expect(screen.getByRole("menu")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("deletes after confirmation", async () => {
    mockDelete.mockResolvedValue(undefined);
    const onDeleted = vi.fn();
    render(
      <ToastProvider>
        <PipelineHeader pipeline={makePipeline({ id: "p1", name: "X" })} onChange={vi.fn()} onDeleted={onDeleted} onDuplicated={vi.fn()} />
      </ToastProvider>
    );
    fireEvent.click(screen.getByRole("button", { name: "Mais ações" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Excluir pipeline" }));
    fireEvent.click(screen.getByRole("button", { name: "Excluir" }));
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith("/api/pipelines/p1"));
    expect(onDeleted).toHaveBeenCalled();
  });

  it("shows the translated error message when deletion fails (409 graph_running)", async () => {
    mockDelete.mockRejectedValue(new ApiError(409, { error: "conflict", code: "graph_running" }));
    const onDeleted = vi.fn();
    render(
      <ToastProvider>
        <PipelineHeader pipeline={makePipeline({ id: "p1" })} onChange={vi.fn()} onDeleted={onDeleted} onDuplicated={vi.fn()} />
      </ToastProvider>
    );
    fireEvent.click(screen.getByRole("button", { name: "Mais ações" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Excluir pipeline" }));
    fireEvent.click(screen.getByRole("button", { name: "Excluir" }));
    expect(await screen.findByText("O pipeline está em execução; aguarde ou pare o run antes de editar.")).toBeInTheDocument();
    expect(onDeleted).not.toHaveBeenCalled();
  });
});
