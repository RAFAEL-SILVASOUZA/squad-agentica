import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { AgentDetail } from "./agent-detail";
import { ToastProvider } from "@/components/ui/toast";
import type { Agent, Skill, CustomTool, MCPServer, KnowledgeBase } from "@/lib/types";

// Mock de next/navigation para os testes de tabs (?tab=).
const mockReplace = vi.fn();
let mockTab = "";
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(mockTab),
  useRouter: () => ({ replace: mockReplace }),
}));

beforeEach(() => {
  mockTab = "";
  mockReplace.mockClear();
  // Mock global de matchMedia (jsdom não implementa).
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
});

afterEach(() => {
  vi.restoreAllMocks();
});

function makeAgent(overrides: Partial<Agent> = {}): Agent {
  return {
    id: "agent-1",
    ownerId: "owner-1",
    name: "Backend Developer",
    type: "Developer",
    description: "Dev de APIs REST.",
    prompt: "Seja um dev sênior.",
    strategy: "iterativo",
    skills: [{ skillId: "code-gen", config: {} }],
    tools: [],
    mcpServers: [],
    knowledge: [],
    integrations: [{ platform: "github", config: {} }],
    inputs: [{ name: "plano_aprovado", type: "object", required: true }],
    outputs: [{ name: "code_pronto", type: "object", required: true }],
    actions: ["follow", "finalize"],
    model: "gpt-4o",
    maxIterations: 5,
    timeout: 300,
    shellAccess: false,
    ...overrides,
  };
}

function makeOptions(): {
  skills: Skill[];
  tools: CustomTool[];
  mcpServers: MCPServer[];
  knowledge: KnowledgeBase[];
} {
  return {
    skills: [
      {
        id: "sk-1",
        name: "code-gen",
        description: "",
        category: "code",
        type: "prompt",
        definition: { template: "", variables: [] },
        inputs: [],
        outputs: [],
        requiredIntegrations: [],
      },
      {
        id: "sk-2",
        name: "test-runner",
        description: "",
        category: "code",
        type: "prompt",
        definition: { template: "", variables: [] },
        inputs: [],
        outputs: [],
        requiredIntegrations: [],
      },
    ],
    tools: [
      {
        id: "tool-1",
        ownerId: "owner-1",
        name: "consultar_jira",
        description: "",
        category: "dev",
        script: "",
        inputs: [],
        outputs: [],
        version: 1,
        status: "deployed",
        createdAt: "",
        updatedAt: "",
      },
    ],
    mcpServers: [
      {
        id: "mcp-1",
        ownerId: "owner-1",
        name: "postgres-readonly",
        description: "",
        transport: "stdio",
        command: "pg",
        env: {},
        status: "connected",
        lastConnectedAt: null,
        discoveredTools: [],
        createdAt: "",
        updatedAt: "",
      },
    ],
    knowledge: [
      {
        id: "kb-1",
        ownerId: "owner-1",
        name: "docs-projeto",
        scope: "global",
        source: "upload",
        reference: "kb-1",
        chunkSize: 512,
        chunkOverlap: 64,
        topK: 5,
        similarityThreshold: 0.7,
        embeddingModel: "text-embedding-3-small",
        embeddingDim: 1536,
        documentCount: 3,
        createdAt: "",
        updatedAt: "",
      },
    ],
  };
}

function renderDetail(props: Partial<React.ComponentProps<typeof AgentDetail>> = {}) {
  const onSave = vi.fn().mockResolvedValue(undefined);
  const utils = render(
    <ToastProvider>
      <AgentDetail
        options={makeOptions()}
        onSave={onSave}
        {...props}
      />
    </ToastProvider>
  );
  return { ...utils, onSave };
}

/** Navega para uma aba clicando no botão da tab. */
function clickTab(name: string) {
  fireEvent.click(screen.getByRole("tab", { name }));
}

describe("AgentDetail", () => {
  // ── Tabs ──────────────────────────────────────────────────────────

  it("renders all five tabs", () => {
    renderDetail({ agent: makeAgent() });
    expect(screen.getByRole("tab", { name: "Visão geral" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Conversar" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Contrato" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Mochila" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Execução" })).toBeInTheDocument();
  });

  it("opens Mochila tab when ?tab=mochila", () => {
    mockTab = "tab=mochila";
    renderDetail({ agent: makeAgent() });
    expect(screen.getByRole("tab", { name: "Mochila" })).toHaveAttribute(
      "aria-selected",
      "true"
    );
  });

  it("navigates to ?tab=execucao when clicking Execução tab", () => {
    renderDetail({ agent: makeAgent() });
    clickTab("Execução");
    expect(mockReplace).toHaveBeenCalledWith(
      expect.stringContaining("tab=execucao"),
      expect.anything()
    );
  });

  // ── Modelo ────────────────────────────────────────────────────────

  it("shows the effective model once in Visão geral", () => {
    renderDetail({
      agent: makeAgent({ model: "gpt-4o", effectiveModel: "Qwen3.8-27B-Q8_0" }),
    });
    // O modelo efetivo aparece em destaque.
    expect(screen.getByText("Qwen3.8-27B-Q8_0")).toBeInTheDocument();
    // A linha "Configurado: …" aparece quando difere.
    expect(
      screen.getByText(/Configurado: gpt-4o/)
    ).toBeInTheDocument();
  });

  it("does not show the configured model as if it were the effective one", () => {
    renderDetail({
      agent: makeAgent({ model: "gpt-4o", effectiveModel: "Qwen3.8-27B-Q8_0" }),
    });
    // "gpt-4o" não aparece como valor de input (só na linha "Configurado:").
    expect(screen.queryByDisplayValue("gpt-4o")).not.toBeInTheDocument();
  });

  it("shows only the model when effectiveModel equals model", () => {
    renderDetail({
      agent: makeAgent({ model: "gpt-4o", effectiveModel: "gpt-4o" }),
    });
    expect(screen.getByText("gpt-4o")).toBeInTheDocument();
    expect(screen.queryByText(/Configurado:/)).not.toBeInTheDocument();
  });

  it("has an editable 'Modelo configurado' field in Execução tab", () => {
    renderDetail({ agent: makeAgent() });
    clickTab("Execução");
    const modelInput = screen.getByLabelText("Modelo configurado");
    expect(modelInput).toHaveValue("gpt-4o");
  });

  // ── Mochila: empty-state links ────────────────────────────────────

  it("shows 'Criar skill →' link when no skills in backpack", () => {
    renderDetail({ agent: makeAgent({ skills: [] }) });
    clickTab("Mochila");
    const link = screen.getByRole("link", { name: /Criar skill/ });
    expect(link).toHaveAttribute("href", "/skills?new=1");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("shows 'Criar tool →' link when no tools in backpack", () => {
    renderDetail({ agent: makeAgent({ tools: [] }) });
    clickTab("Mochila");
    const link = screen.getByRole("link", { name: /Criar tool/ });
    expect(link).toHaveAttribute("href", "/tools?new=1");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("shows 'Criar base →' link when no knowledge in backpack", () => {
    renderDetail({ agent: makeAgent({ knowledge: [] }) });
    clickTab("Mochila");
    const link = screen.getByRole("link", { name: /Criar base/ });
    expect(link).toHaveAttribute("href", "/knowledge?new=1");
    expect(link).toHaveAttribute("target", "_blank");
  });

  // ── Mobile sticky (matchMedia < 768px) ────────────────────────────

  it("applies position:sticky to the chat input on mobile (<768px)", () => {
    // Mock matchMedia para mobile.
    const mockMql = { matches: true, media: "(max-width: 767px)", addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn(), onchange: null, dispatchEvent: vi.fn() };
    vi.spyOn(window, "matchMedia").mockReturnValue(mockMql as unknown as MediaQueryList);

    renderDetail({ agent: makeAgent(), chatPath: "/api/agents/agent-1/chat" });
    clickTab("Conversar");

    // O campo de mensagem (input do chat) deve ter position: sticky.
    const chatInput = screen.getByLabelText("Mensagem");
    expect(chatInput).toHaveStyle({ position: "sticky", bottom: "0" });
  });

  // ── Funcionalidade existente (mantida) ────────────────────────────

  it("pre-fills identity fields from an existing agent", () => {
    renderDetail({ agent: makeAgent() });
    expect(screen.getByDisplayValue("Backend Developer")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Dev de APIs REST.")).toBeInTheDocument();
  });

  it("requires a name before saving", async () => {
    const { onSave } = renderDetail({ agent: makeAgent({ name: "" }) });
    fireEvent.click(screen.getByRole("button", { name: /salvar/i }));
    await waitFor(() => {
      expect(screen.getByText("Informe um nome para o agente.")).toBeInTheDocument();
    });
    expect(onSave).not.toHaveBeenCalled();
  });

  it("saves with the edited name", async () => {
    const { onSave } = renderDetail({ agent: makeAgent() });
    const nameInput = screen.getByDisplayValue("Backend Developer");
    fireEvent.change(nameInput, { target: { value: "Novo Nome" } });
    fireEvent.click(screen.getByRole("button", { name: /salvar/i }));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalled();
    });
    const payload = onSave.mock.calls[0][0];
    expect(payload.name).toBe("Novo Nome");
  });

  it("saves a port's description in the payload (Contrato tab)", async () => {
    const { onSave } = renderDetail({ agent: makeAgent() });
    clickTab("Contrato");
    const descInputs = screen.getAllByLabelText("Descrição do port 1");
    fireEvent.change(descInputs[0], {
      target: { value: "Plano aprovado pelo cliente" },
    });
    fireEvent.click(screen.getByRole("button", { name: /salvar/i }));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalled();
    });
    const payload = onSave.mock.calls[0][0];
    expect(payload.inputs).toEqual([
      {
        name: "plano_aprovado",
        type: "object",
        required: true,
        description: "Plano aprovado pelo cliente",
      },
    ]);
  });

  it("toggles an action in Contrato tab", async () => {
    const { onSave } = renderDetail({ agent: makeAgent() });
    clickTab("Contrato");
    fireEvent.click(screen.getByRole("button", { name: "Devolver" }));
    fireEvent.click(screen.getByRole("button", { name: /salvar/i }));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalled();
    });
    const payload = onSave.mock.calls[0][0];
    expect(payload.actions).toContain("return");
  });

  it("adds a skill from the selector in Mochila tab", async () => {
    const { onSave } = renderDetail({ agent: makeAgent({ skills: [] }) });
    clickTab("Mochila");
    const skillSelect = screen.getByLabelText("Selecionar skill");
    fireEvent.change(skillSelect, { target: { value: "sk-2" } });
    fireEvent.click(screen.getByRole("button", { name: "Adicionar skill" }));
    fireEvent.click(screen.getByRole("button", { name: /salvar/i }));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalled();
    });
    const payload = onSave.mock.calls[0][0];
    expect(payload.skills).toEqual([{ skillId: "sk-2", config: {} }]);
  });

  it("shows the skill name, not its id, on the backpack chip (E3)", () => {
    renderDetail({ agent: makeAgent({ skills: [] }) });
    clickTab("Mochila");
    fireEvent.change(screen.getByLabelText("Selecionar skill"), { target: { value: "sk-2" } });
    fireEvent.click(screen.getByRole("button", { name: "Adicionar skill" }));
    expect(screen.getByRole("button", { name: "Remover test-runner" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remover sk-2" })).not.toBeInTheDocument();
  });

  it("adds an integration from the selector in Mochila tab", async () => {
    const { onSave } = renderDetail({ agent: makeAgent({ integrations: [] }) });
    clickTab("Mochila");
    const integSelect = screen.getByLabelText("Selecionar integração");
    fireEvent.change(integSelect, { target: { value: "gitlab" } });
    fireEvent.click(screen.getByRole("button", { name: "Adicionar integração" }));
    fireEvent.click(screen.getByRole("button", { name: /salvar/i }));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalled();
    });
    const payload = onSave.mock.calls[0][0];
    expect(payload.integrations).toEqual([{ platform: "gitlab", config: {} }]);
  });

  it("toggles shellAccess in Execução tab", async () => {
    const { onSave } = renderDetail({ agent: makeAgent({ shellAccess: false }) });
    clickTab("Execução");
    fireEvent.click(screen.getByRole("switch", { name: "Acesso a shell" }));
    fireEvent.click(screen.getByRole("button", { name: /salvar/i }));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalled();
    });
    const payload = onSave.mock.calls[0][0];
    expect(payload.shellAccess).toBe(true);
  });

  it("shows empty backpack hints when no options (Mochila tab)", () => {
    render(
      <ToastProvider>
        <AgentDetail
          options={{ skills: [], tools: [], mcpServers: [], knowledge: [] }}
          onSave={vi.fn()}
        />
      </ToastProvider>
    );
    clickTab("Mochila");
    expect(screen.getByText("Nenhuma skill cadastrada")).toBeInTheDocument();
    expect(screen.getByText("Nenhuma tool cadastrada")).toBeInTheDocument();
    expect(screen.getByText("Nenhum servidor cadastrado")).toBeInTheDocument();
    expect(screen.getByText("Nenhuma base cadastrada")).toBeInTheDocument();
  });

  it("syncs the form when the agent prop changes (config_update via chat)", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const { rerender } = render(
      <ToastProvider>
        <AgentDetail
          options={makeOptions()}
          onSave={onSave}
          agent={makeAgent()}
        />
      </ToastProvider>
    );

    expect(screen.getByDisplayValue("Backend Developer")).toBeInTheDocument();
    expect(screen.getByDisplayValue("iterativo")).toBeInTheDocument();

    rerender(
      <ToastProvider>
        <AgentDetail
          options={makeOptions()}
          onSave={onSave}
          agent={makeAgent({ name: "Dev Ajustado", strategy: "paralelo" })}
        />
      </ToastProvider>
    );

    expect(screen.getByDisplayValue("Dev Ajustado")).toBeInTheDocument();
    expect(screen.getByDisplayValue("paralelo")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /salvar/i }));
    await waitFor(() => {
      expect(onSave).toHaveBeenCalled();
    });
    const payload = onSave.mock.calls[0][0];
    expect(payload.name).toBe("Dev Ajustado");
    expect(payload.strategy).toBe("paralelo");
  });
});
