import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ApprovalQueue } from "./approval-queue";
import { ToastProvider } from "@/components/ui/toast";

const mocks = vi.hoisted(() => ({ list: vi.fn(), get: vi.fn(), post: vi.fn(), delete: vi.fn() }));

vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  api: mocks,
}));
vi.mock("@/lib/websocket", () => ({
  getWebSocketClient: () => ({ on: vi.fn(), off: vi.fn(), onReconnect: vi.fn(), connect: vi.fn() }),
  disposeWebSocketClient: vi.fn(),
}));

const approval = {
  id: "a1",
  pipelineId: "p1",
  agentId: "ag1",
  checkpointId: "cp1",
  message: "Aprovar especificação?",
  context: { especificacao: "Fazer login com OAuth" },
  status: "pending" as const,
  channel: "in-app" as const,
  sentAt: new Date(Date.now() - 12 * 60_000).toISOString(),
  retryCount: 0,
  maxRetries: 3,
  attemptedChannels: ["in-app"],
  fallbackChannel: null,
  timeoutSeconds: 300,
  nodeId: "node-revisor",
  runId: "run-1",
};

const pipelines = [{ id: "p1", name: "Pipeline de Login" }];
const agents = [{ id: "ag1", name: "Revisor" }];

function mockList(path: string, opts?: { page?: number; limit?: number; query?: Record<string, string | number | boolean | undefined> }) {
  if (path === "/api/approvals") {
    // "resolved" não tem itens no mock (a aprovação é pending).
    if (opts?.query?.status === "resolved") return { items: [], total: 0, page: 1, limit: 50 };
    return { items: [approval], total: 1, page: 1, limit: 50 };
  }
  if (path === "/api/pipelines") return { items: pipelines, total: 1, page: 1, limit: 100 };
  if (path === "/api/agents") return { items: agents, total: 1, page: 1, limit: 100 };
  return { items: [], total: 0, page: 1, limit: 50 };
}

const show = (props?: Record<string, unknown>) =>
  render(<ToastProvider><ApprovalQueue {...props} /></ToastProvider>);

beforeEach(() => {
  vi.clearAllMocks();
  mocks.list.mockImplementation((path: string, opts?: { page?: number; limit?: number; query?: Record<string, string | number | boolean | undefined> }) => Promise.resolve(mockList(path, opts)));
  mocks.post.mockResolvedValue({ approvalId: "a1", status: "approved", respondedAt: "" });
  mocks.delete.mockResolvedValue({});
  mocks.get.mockResolvedValue({ items: [] });
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false, media: query, onchange: null,
      addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    })),
  });
});

describe("ApprovalQueue", () => {
  it("mostra pipeline, nó e tempo relativo", async () => {
    show();
    expect(await screen.findByText("Aprovar especificação?")).toBeInTheDocument();
    expect(screen.getByText(/Pipeline de Login/)).toBeInTheDocument();
    expect(screen.getByText(/Revisor/)).toBeInTheDocument();
    expect(screen.getByText(/há 12 min/)).toBeInTheDocument();
  });

  it("Aprovar chama respond com approved e remove o card", async () => {
    show();
    await screen.findByText("Aprovar especificação?");
    fireEvent.click(screen.getByRole("button", { name: /Aprovar/ }));
    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith("/api/approvals/a1/respond", { decision: "approved", response: null }));
    await waitFor(() => expect(screen.queryByText("Aprovar especificação?")).not.toBeInTheDocument());
  });

  it("Argumentar sem texto deixa Enviar desabilitado", async () => {
    show();
    await screen.findByText("Aprovar especificação?");
    fireEvent.click(screen.getByRole("button", { name: /Argumentar/ }));
    const sendBtn = screen.getByRole("button", { name: /Enviar argumento/ });
    expect(sendBtn).toBeDisabled();
  });

  it("Argumentar com texto envia revised com feedback", async () => {
    show();
    await screen.findByText("Aprovar especificação?");
    fireEvent.click(screen.getByRole("button", { name: /Argumentar/ }));
    const textarea = screen.getByLabelText("Argumento");
    fireEvent.change(textarea, { target: { value: "Corrija o escopo" } });
    fireEvent.click(screen.getByRole("button", { name: /Enviar argumento/ }));
    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith("/api/approvals/a1/respond", { decision: "revised", response: "Corrija o escopo" }));
  });

  it("Rejeitar pede confirmação", async () => {
    show();
    await screen.findByText("Aprovar especificação?");
    fireEvent.click(screen.getByRole("button", { name: /Rejeitar/ }));
    // Deve aparecer um diálogo de confirmação
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Confirmar rejeição")).toBeInTheDocument();
    // Cancelar não chama a API
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it("filtro Respondidas chama API com status=resolved", async () => {
    show({ status: "resolved" });
    await screen.findByText(/Nenhuma aprovação respondida/);
    expect(mocks.list).toHaveBeenCalledWith("/api/approvals", expect.objectContaining({ query: expect.objectContaining({ status: "resolved" }) }));
  });

  it("Ver contexto tem href com tab=resultado e node", async () => {
    show();
    await screen.findByText("Aprovar especificação?");
    const link = screen.getByRole("link", { name: /Ver contexto/ });
    expect(link).toHaveAttribute("href", "/pipelines/p1/run?tab=resultado&node=node-revisor");
  });

  it("fila vazia mostra link Como funcionam as aprovações", async () => {
    mocks.list.mockImplementation((path: string) =>
      Promise.resolve(path === "/api/approvals" ? { items: [], total: 0, page: 1, limit: 50 } : mockList(path))
    );
    show();
    const btn = await screen.findByRole("button", { name: /Como funcionam as aprovações/ });
    fireEvent.click(btn);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Como funcionam as aprovações?")).toBeInTheDocument();
    expect(within(dialog).getByText(/Aprovar/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Argumentar/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Rejeitar/)).toBeInTheDocument();
  });
});
