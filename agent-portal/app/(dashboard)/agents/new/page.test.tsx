import * as React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import NewAgentPage from "./page";

// ─── Mocks ────────────────────────────────────────────────────────────────

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
const mockGet = vi.fn();
vi.mock("@/lib/api", () => ({
  api: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    list: (...args: unknown[]) => mockList(...args),
  },
  ApiError: class ApiError extends Error {
    status: number;
    code: string;
    method?: string;
    path?: string;
    constructor(status: number, body: { error: string; code: string }) {
      super(body.error);
      this.name = "ApiError";
      this.status = status;
      this.code = body.code;
    }
    describe() {
      if (this.method && this.path) {
        return `HTTP ${this.status} · ${this.method} ${this.path}`;
      }
      return `HTTP ${this.status}`;
    }
  },
}));

const mockConfirm = vi.fn();
const mockRestore = vi.fn();
vi.mock("@/lib/agent-chat", () => ({
  confirmAgentDraft: (...args: unknown[]) => mockConfirm(...args),
  restoreAgentDraft: (...args: unknown[]) => mockRestore(...args),
}));

// Stubs que expõem as props para o teste.
type AgentChatStubProps = {
  draftId: string | null;
  onDraftId?: (id: string) => void;
  onConfigUpdate?: (config: Partial<Record<string, unknown>>) => void;
};
type AgentPreviewStubProps = {
  config: Partial<Record<string, unknown>>;
  onValidate?: (state: { valid: boolean; missing: string[] }) => void;
};
vi.mock("@/components/agents", () => ({
  AgentChat: (props: AgentChatStubProps) => (
    <div data-testid="agent-chat" data-draft-id={props.draftId ?? "null"}>
      <button
        onClick={() =>
          props.onDraftId?.("d-1")
        }
        aria-label="mock draft"
      >
        mock draft
      </button>
      <button
        onClick={() => props.onConfigUpdate?.({ name: "Resumidor" })}
        aria-label="mock config"
      >
        mock config
      </button>
    </div>
  ),
  AgentPreview: (props: AgentPreviewStubProps) => (
    <div data-testid="agent-preview" data-config-name={String(props.config.name ?? "")}>
      {props.config.name ? String(props.config.name) : null}
      <button
        onClick={() => props.onValidate?.({ valid: false, missing: ["name"] })}
        aria-label="mock invalid"
      >
        mock invalid
      </button>
      <button
        onClick={() => props.onValidate?.({ valid: true, missing: [] })}
        aria-label="mock valid"
      >
        mock valid
      </button>
    </div>
  ),
}));

const EMPTY_ITEMS = { items: [], total: 0, page: 1, limit: 100 };

function renderPage() {
  return render(<NewAgentPage />);
}

function mockBackpack() {
  mockList.mockResolvedValue(EMPTY_ITEMS);
}

function mockSuccessfulConfirm() {
  mockConfirm.mockResolvedValue({ id: "agent-1", name: "Resumidor" });
}

beforeEach(() => {
  vi.clearAllMocks();
  window.sessionStorage.clear();
  mockBackpack();
});

afterEach(() => {
  vi.useRealTimers();
  window.sessionStorage.clear();
});

// ─── draftId em sessionStorage ────────────────────────────────────────────

describe("draftId em sessionStorage", () => {
  it("guarda o draftId na chave agent-draft-id quando o chat cria um draft", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "mock draft" }));

    expect(window.sessionStorage.getItem("agent-draft-id")).toBe("d-1");
  });

  it("retoma o draft guardado ao montar (passa o draftId para o chat)", async () => {
    window.sessionStorage.setItem("agent-draft-id", "d-7");
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("agent-chat")).toHaveAttribute(
        "data-draft-id",
        "d-7"
      );
    });
  });

  it("remove a chave do sessionStorage após o salvamento com sucesso", async () => {
    const user = userEvent.setup();
    mockSuccessfulConfirm();
    renderPage();

    await user.click(screen.getByLabelText("mock draft"));
    await user.click(screen.getByRole("button", { name: /salvar agente/i }));

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/agents/agent-1"));
    expect(window.sessionStorage.getItem("agent-draft-id")).toBeNull();
  });
});

// ─── Erros de salvamento ──────────────────────────────────────────────────

describe("salvar com erro", () => {
  it("404 draft_not_found: ErrorPanel 'O rascunho expirou no servidor' com recriação", async () => {
    const user = userEvent.setup();
    window.sessionStorage.setItem("agent-draft-id", "d-antigo");
    const expired = new Error("Recurso não encontrado.");
    Object.assign(expired, { status: 404, code: "draft_not_found" });
    mockConfirm.mockRejectedValueOnce(expired);
    mockRestore.mockResolvedValue({ draftId: "d-novo" });
    mockSuccessfulConfirm();
    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("agent-chat")).toHaveAttribute(
        "data-draft-id",
        "d-antigo"
      )
    );
    // Preenche o preview (config atual da tela).
    await user.click(screen.getByLabelText("mock config"));

    await user.click(screen.getByRole("button", { name: /salvar agente/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("O rascunho expirou no servidor");
    expect(
      screen.queryByRole("button", { name: /tentar de novo/i })
    ).not.toBeInTheDocument();

    // Recriar a partir do que está na tela: restore com a config atual e
    // depois confirm; o fluxo termina com sucesso.
    await user.click(
      screen.getByRole("button", { name: "Recriar a partir do que está na tela" })
    );

    await waitFor(() => expect(mockRestore).toHaveBeenCalledTimes(1));
    const restoreCall = mockRestore.mock.calls[0][0] as Record<string, unknown>;
    expect(restoreCall).toHaveProperty("name", expect.anything());
    await waitFor(() =>
      expect(mockConfirm).toHaveBeenLastCalledWith("d-novo")
    );
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/agents/agent-1"));
    // Sucesso final: a chave é limpa (o agente já existe, o rascunho não).
    expect(window.sessionStorage.getItem("agent-draft-id")).toBeNull();
  });

  it("outro erro: ErrorPanel 'Tentar de novo' e o preview permanece preenchido", async () => {
    const user = userEvent.setup();
    window.sessionStorage.setItem("agent-draft-id", "d-1");
    mockConfirm.mockRejectedValueOnce(new Error("Já existe um agente com este nome."));
    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId("agent-chat")).toHaveAttribute(
        "data-draft-id",
        "d-1"
      )
    );
    // Preenche o preview.
    await user.click(screen.getByLabelText("mock config"));
    expect(screen.getByTestId("agent-preview")).toHaveAttribute(
      "data-config-name",
      "Resumidor"
    );

    await user.click(screen.getByRole("button", { name: /salvar agente/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Não foi possível salvar o agente");
    expect(
      screen.getByRole("button", { name: /tentar de novo/i })
    ).toBeInTheDocument();
    // Preview continua preenchido (estado preservado).
    expect(screen.getByTestId("agent-preview")).toHaveAttribute(
      "data-config-name",
      "Resumidor"
    );

    // "Tentar de novo" reenvia o mesmo confirm.
    const callsBefore = mockConfirm.mock.calls.length;
    await user.click(screen.getByRole("button", { name: /tentar de novo/i }));
    await waitFor(() => expect(mockConfirm.mock.calls.length).toBe(callsBefore + 1));
  });
});

// ─── Validação do preview ─────────────────────────────────────────────────

describe("validação do preview", () => {
  it("desabilita Salvar enquanto a validação diz valid=false", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByLabelText("mock draft"));
    await user.click(screen.getByLabelText("mock config"));
    await user.click(screen.getByLabelText("mock invalid"));

    const save = screen.getByRole("button", { name: /salvar agente/i });
    expect(save).toBeDisabled();

    await user.click(screen.getByLabelText("mock valid"));
    expect(save).toBeEnabled();
  });
});
