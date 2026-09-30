import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import AgentDetailPage from "./page";
import type {
  Agent,
  Skill,
  CustomTool,
  MCPServer,
  KnowledgeBase,
} from "@/lib/types";

// Mocks de next/navigation, api, toast e componentes de agents.
const mockPush = vi.fn();
const mockParams = { id: "agent-1" };

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  useParams: () => mockParams,
}));

const mockAddToast = vi.fn();
vi.mock("@/components/ui/toast", () => ({
  useToast: () => ({ addToast: mockAddToast }),
}));

const mockGet = vi.fn();
const mockPut = vi.fn();
const mockDelete = vi.fn();
const mockList = vi.fn();
vi.mock("@/lib/api", () => ({
  api: {
    get: (...args: unknown[]) => mockGet(...args),
    put: (...args: unknown[]) => mockPut(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
    list: (...args: unknown[]) => mockList(...args),
  },
  ApiError: class ApiError extends Error {
    status: number;
    code: string;
    details?: Record<string, unknown>;
    constructor(status: number, body: { error: string; code: string }) {
      super(body.error);
      this.status = status;
      this.code = body.code;
    }
  },
}));

// Mock do chat (SSE) para simular config_update em modo edição.
// O onConfigUpdate agora é capturado do AgentDetail (o chat vive na aba Conversar).
let configUpdateHandler: ((config: Partial<Agent>) => void) | null = null;
vi.mock("@/components/agents", () => ({
  AgentChat: (props: {
    chatPath: string;
    onConfigUpdate?: (config: Partial<Agent>) => void;
  }) => {
    configUpdateHandler = props.onConfigUpdate ?? null;
    return (
      <div data-testid="agent-chat" data-chat-path={props.chatPath} />
    );
  },
  AgentDetail: (props: {
    agent: Agent;
    options: unknown;
    onSave: (payload: Record<string, unknown>) => Promise<void>;
    saving?: boolean;
    chatConfig?: Partial<Agent>;
    onConfigUpdate?: (config: Partial<Agent>) => void;
  }) => {
    // Captura o handler de config_update (o chat real vive na aba Conversar).
    configUpdateHandler = props.onConfigUpdate ?? null;
    // O preview agora vive dentro do AgentDetail (aba Conversar); o mock
    // reflete a fusão agent + chatConfig, como o componente real faz.
    const merged =
      props.chatConfig && Object.keys(props.chatConfig).length > 0
        ? ({ ...props.agent, ...props.chatConfig } as Agent)
        : props.agent;
    return (
      <div data-testid="agent-detail" data-agent-name={merged.name}>
        <div
          data-testid="agent-preview"
          data-preview-name={merged.name ?? ""}
        />
        <button
          data-testid="save-agent"
          onClick={() => props.onSave({ name: merged.name })}
        >
          Salvar
        </button>
      </div>
    );
  },
  DeleteAgentModal: (props: {
    open: boolean;
    agentName: string;
    onConfirm: () => void;
    onCancel: () => void;
  }) =>
    props.open ? (
      <div data-testid="delete-modal" data-agent-name={props.agentName}>
        <button data-testid="confirm-delete" onClick={props.onConfirm}>
          Confirmar
        </button>
      </div>
    ) : null,
}));

function makeAgent(overrides: Partial<Agent> = {}): Agent {
  return {
    id: "agent-1",
    ownerId: "owner-1",
    name: "Backend Developer",
    type: "Developer",
    description: "Dev de APIs REST.",
    prompt: "Seja um dev sênior.",
    strategy: "iterativo",
    skills: [],
    tools: [],
    mcpServers: [],
    knowledge: [],
    integrations: [],
    inputs: [],
    outputs: [],
    actions: ["follow"],
    model: "gpt-4o",
    maxIterations: 5,
    timeout: 300,
    shellAccess: false,
    ...overrides,
  };
}

function makeBackpack(): {
  skills: Skill[];
  tools: CustomTool[];
  mcpServers: MCPServer[];
  knowledge: KnowledgeBase[];
} {
  return { skills: [], tools: [], mcpServers: [], knowledge: [] };
}

function mockBackpack() {
  mockList.mockImplementation((path: string) => {
    if (path.startsWith("/api/skills") ||
        path.startsWith("/api/tools") ||
        path.startsWith("/api/mcp-servers") ||
        path.startsWith("/api/knowledge")) {
      return Promise.resolve({
        items: (makeBackpack() as Record<string, unknown[]>)[
          path.includes("skills")
            ? "skills"
            : path.includes("tools")
            ? "tools"
            : path.includes("mcp-servers")
            ? "mcpServers"
            : "knowledge"
        ],
        total: 0,
        page: 1,
        limit: 100,
      });
    }
    return Promise.resolve({ items: [], total: 0, page: 1, limit: 100 });
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  configUpdateHandler = null;
});

describe("AgentDetailPage", () => {
  it("shows not found state for 404", async () => {
    const { ApiError } = await import("@/lib/api");
    mockGet.mockRejectedValue(
      new ApiError(404, { error: "not found", code: "not_found" })
    );
    mockBackpack();

    render(<AgentDetailPage />);

    await waitFor(() => {
      expect(screen.getByText("Agente não encontrado")).toBeInTheDocument();
    });
  });

  it("shows error with retry on API failure", async () => {
    mockGet.mockRejectedValue(new Error("boom"));
    mockBackpack();

    render(<AgentDetailPage />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /tentar novamente/i })
      ).toBeInTheDocument();
    });
  });

  it("renders agent name and detail after load", async () => {
    mockGet.mockResolvedValue(makeAgent());
    mockBackpack();

    render(<AgentDetailPage />);

    await waitFor(() => {
      expect(screen.getByTestId("agent-detail")).toBeInTheDocument();
    });
    expect(screen.getByTestId("agent-detail")).toHaveAttribute(
      "data-agent-name",
      "Backend Developer"
    );
  });

  it("applies config_update from the edit chat to the form and preview", async () => {
    mockGet.mockResolvedValue(makeAgent());
    mockBackpack();

    render(<AgentDetailPage />);

    await waitFor(() => {
      expect(screen.getByTestId("agent-detail")).toBeInTheDocument();
    });

    // Simula o evento config_update do chat de edição.
    // O modo edição devolve a config COMPLETA do draft (build_preview).
    const fullConfig = makeAgent({
      name: "Backend Dev Ajustado",
      strategy: "paralelo",
    });
    configUpdateHandler?.(fullConfig);

    await waitFor(() => {
      expect(screen.getByTestId("agent-detail")).toHaveAttribute(
        "data-agent-name",
        "Backend Dev Ajustado"
      );
    });
    expect(screen.getByTestId("agent-preview")).toHaveAttribute(
      "data-preview-name",
      "Backend Dev Ajustado"
    );
  });

  it("saves the chat-updated agent via PUT and shows toast", async () => {
    mockGet.mockResolvedValue(makeAgent());
    mockBackpack();
    const updated = makeAgent({ name: "Backend Dev Ajustado" });
    mockPut.mockResolvedValue(updated);

    render(<AgentDetailPage />);

    await waitFor(() => {
      expect(screen.getByTestId("agent-detail")).toBeInTheDocument();
    });

    configUpdateHandler?.(makeAgent({ name: "Backend Dev Ajustado" }));

    await waitFor(() => {
      expect(screen.getByTestId("agent-detail")).toHaveAttribute(
        "data-agent-name",
        "Backend Dev Ajustado"
      );
    });

    screen.getByTestId("save-agent").click();

    await waitFor(() => {
      expect(mockPut).toHaveBeenCalledWith(
        "/api/agents/agent-1",
        expect.objectContaining({ name: "Backend Dev Ajustado" })
      );
    });
    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith("success", "Agente atualizado.");
    });
  });

  it("deletes the agent via modal and navigates to dashboard", async () => {
    mockGet.mockResolvedValue(makeAgent());
    mockBackpack();
    mockDelete.mockResolvedValue(undefined);

    render(<AgentDetailPage />);

    await waitFor(() => {
      expect(screen.getByTestId("agent-detail")).toBeInTheDocument();
    });

    // Abre o modal de exclusão.
    screen.getByRole("button", { name: /excluir/i }).click();

    await waitFor(() => {
      expect(screen.getByTestId("delete-modal")).toBeInTheDocument();
    });

    screen.getByTestId("confirm-delete").click();

    await waitFor(() => {
      expect(mockDelete).toHaveBeenCalledWith("/api/agents/agent-1");
    });
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/");
    });
  });
});
