import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { IntegrationsView } from "./integrations-view";
import { ToastProvider } from "@/components/ui/toast";
import { ApiError } from "@/lib/api";

const mocks = vi.hoisted(() => ({ list: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), replace: vi.fn(), tab: "" }));
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), api: mocks }));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(mocks.tab), useRouter: () => ({ replace: mocks.replace }) }));
const gh = { id: "1", type: "github", name: "Meu GitHub", config: { token: "***" }, status: "active" };
const az = { id: "2", type: "azure", name: "Azure Org", config: { token: "***", organization: "org" }, status: "active" };
const page = (items: unknown[]) => ({ items, total: items.length, page: 1, limit: 100 });
const show = () => render(<ToastProvider><IntegrationsView /></ToastProvider>);
beforeEach(() => { vi.clearAllMocks(); mocks.tab = ""; mocks.list.mockResolvedValue(page([gh, az])); });

describe("IntegrationsView", () => {
  it("filters providers and supports keyboard tabs and query navigation", async () => {
    show();
    expect(await screen.findByText("Meu GitHub")).toBeInTheDocument();
    expect(screen.queryByText("Azure Org")).not.toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole("tab", { name: "GitHub" }), { key: "ArrowRight" });
    expect(await screen.findByText("Azure Org")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Azure DevOps" })).toHaveAttribute("aria-selected", "true");
    expect(mocks.replace).toHaveBeenCalledWith("/integrations?tab=azure", { scroll: false });
  });
  it("opens the query tab and preserves the disabled Rivvn message", () => {
    mocks.tab = "tab=outras"; show();
    expect(screen.getByRole("tab", { name: "Outras" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText(/apenas para clientes com contrato ativo/)).toBeInTheDocument();
  });
  it.each(["azure", "github"])("creates %s with only its required fields and a masked input", async (provider) => {
    mocks.tab = `tab=${provider}`; show();
    fireEvent.click(await screen.findByRole("button", { name: "Nova conexão" }));
    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Nova" } });
    if (provider === "azure") fireEvent.change(screen.getByLabelText("Organização"), { target: { value: "org" } });
    else expect(screen.queryByLabelText(/owner|organização/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Token")).toHaveAttribute("type", "password");
    fireEvent.change(screen.getByLabelText("Token"), { target: { value: "pat-123" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar conexão" }));
    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith("/api/integrations", { type: provider, name: "Nova", config: { token: "pat-123", ...(provider === "azure" ? { organization: "org" } : {}) } }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.queryByDisplayValue("pat-123")).not.toBeInTheDocument();
  });
  it("falha no save vira painel inline com 'Tentar de novo' e detalhe com o contexto da API", async () => {
    const saveError = new ApiError(400, { error: "validation error", code: "secret_key_missing" });
    saveError.method = "POST";
    saveError.path = "/api/integrations";
    mocks.post.mockRejectedValue(saveError);
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Nova conexão" }));
    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Nova" } });
    fireEvent.change(screen.getByLabelText("Token"), { target: { value: "pat-123" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar conexão" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Não foi possível salvar a conexão");
    // O detalhe técnico (HTTP 400 · POST /api/integrations) fica recolhido.
    fireEvent.click(screen.getByRole("button", { name: "Ver detalhes" }));
    expect(alert).toHaveTextContent("HTTP 400 · POST /api/integrations");
    expect(screen.getByRole("button", { name: "Tentar de novo" })).toBeInTheDocument();
  });
  it("preserves the token when editing without a replacement", async () => {
    show(); fireEvent.click(await screen.findByRole("button", { name: "Editar Meu GitHub" }));
    expect(screen.getByLabelText("Token")).toHaveValue("");
    fireEvent.click(screen.getByRole("button", { name: "Salvar conexão" }));
    await waitFor(() => expect(mocks.put).toHaveBeenCalledWith("/api/integrations/1", { name: "Meu GitHub", config: { token: "***" } }));
  });
  it.each([{ ok: false, error: "Token inválido ou sem acesso" }, { ok: true, repositories: 3 }])("shows the test result $ok", async (result) => {
    mocks.post.mockResolvedValue(result); show();
    fireEvent.click(await screen.findByRole("button", { name: "Testar conexão Meu GitHub" }));
    expect(await screen.findByText(result.ok ? "Conectado, 3 repositórios" : result.error!)).toBeInTheDocument();
  });
  it("lists affected pipelines before confirming deletion", async () => {
    mocks.list.mockImplementation((path: string) => Promise.resolve(page(path === "/api/pipelines" ? [{ id: "p", name: "Gerador", repository: { integrationId: "1" } }] : [gh])));
    show(); fireEvent.click(await screen.findByRole("button", { name: "Excluir Meu GitHub" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("O pipeline Gerador ficará sem repositório.")).toBeInTheDocument();
    expect(mocks.delete).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Excluir conexão" }));
    await waitFor(() => expect(mocks.delete).toHaveBeenCalledWith("/api/integrations/1"));
  });
  it("joins three affected pipeline names in pt-BR (A, B e C)", async () => {
    mocks.list.mockImplementation((path: string) => Promise.resolve(page(path === "/api/pipelines" ? [
      { id: "p1", name: "Gerador", repository: { integrationId: "1" } },
      { id: "p2", name: "Revisor", repository: { integrationId: "1" } },
      { id: "p3", name: "Publicador", repository: { integrationId: "1" } },
    ] : [gh])));
    show(); fireEvent.click(await screen.findByRole("button", { name: "Excluir Meu GitHub" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("Os pipelines Gerador, Revisor e Publicador ficarão sem repositório.")).toBeInTheDocument();
  });
});
