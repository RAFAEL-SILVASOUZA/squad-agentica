import { render, screen, waitFor, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { AgentPreview } from "./agent-preview";
import type { Agent } from "@/lib/types";

// ─── Mocks ────────────────────────────────────────────────────────

const mockPost = vi.fn();
vi.mock("@/lib/api", () => ({
  api: {
    post: (...args: unknown[]) => mockPost(...args),
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

function makeConfig(overrides: Partial<Agent> = {}): Partial<Agent> {
  return {
    name: "Backend Developer",
    type: "Developer",
    description: "Desenvolve APIs REST em Python.",
    model: "gpt-4o",
    maxIterations: 5,
    timeout: 300,
    shellAccess: false,
    skills: [{ skillId: "code-gen", config: {} }],
    tools: [{ toolId: "consultar_jira", config: {} }],
    mcpServers: [{ serverId: "postgres-readonly" }],
    knowledge: [{ source: "upload", reference: "docs-projeto" }],
    integrations: [{ platform: "github", config: {} }],
    inputs: [{ name: "plano_aprovado", type: "object", required: true }],
    outputs: [
      { name: "code_pronto", type: "object", required: true },
      { name: "code_com_erro", type: "object", required: false },
    ],
    actions: ["follow", "return", "finalize"],
    ...overrides,
  };
}

describe("AgentPreview", () => {
  it("shows empty hint when config is empty", () => {
    mockPost.mockResolvedValue({ valid: true, missing: [], errors: [] });
    render(<AgentPreview config={{}} />);
    expect(
      screen.getByText("Descreva o agente no chat para ver o preview aqui.")
    ).toBeInTheDocument();
  });

  it("shows streaming hint when empty and streaming", () => {
    render(<AgentPreview config={{}} streaming />);
    expect(screen.getByText("Gerando configuração…")).toBeInTheDocument();
  });

  it("renders identity, execution and contract", () => {
    mockPost.mockResolvedValue({ valid: true, missing: [], errors: [] });
    render(<AgentPreview config={makeConfig()} />);
    expect(screen.getByText("Backend Developer")).toBeInTheDocument();
    expect(screen.getByText("Developer")).toBeInTheDocument();
    expect(screen.getByText("gpt-4o")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("300s")).toBeInTheDocument();
    expect(screen.getByText("Desativado")).toBeInTheDocument();
    expect(screen.getByText("plano_aprovado")).toBeInTheDocument();
    expect(screen.getByText("code_pronto, code_com_erro")).toBeInTheDocument();
    expect(screen.getByText("seguir · devolver · finalizar")).toBeInTheDocument();
  });

  it("shows the server-defined model when it differs from the agent model", () => {
    mockPost.mockResolvedValue({ valid: true, missing: [], errors: [] });
    render(<AgentPreview config={makeConfig({ effectiveModel: "Qwen3.8-27B-Q8_0" })} />);
    expect(screen.getByText("Qwen3.8-27B-Q8_0 (definido pelo servidor)")).toBeInTheDocument();
  });

  it("shows only the agent model when effectiveModel is equal", () => {
    mockPost.mockResolvedValue({ valid: true, missing: [], errors: [] });
    render(<AgentPreview config={makeConfig({ effectiveModel: "gpt-4o" })} />);
    expect(screen.getByText("gpt-4o")).toBeInTheDocument();
    expect(screen.queryByText(/definido pelo servidor/)).not.toBeInTheDocument();
  });

  it("renders backpack chips", () => {
    mockPost.mockResolvedValue({ valid: true, missing: [], errors: [] });
    render(<AgentPreview config={makeConfig()} />);
    expect(screen.getByText("code-gen")).toBeInTheDocument();
    expect(screen.getByText("consultar_jira")).toBeInTheDocument();
    expect(screen.getByText("postgres-readonly")).toBeInTheDocument();
    expect(screen.getByText("docs-projeto")).toBeInTheDocument();
    expect(screen.getByText("github")).toBeInTheDocument();
  });

  it("hides empty sections", () => {
    mockPost.mockResolvedValue({ valid: true, missing: [], errors: [] });
    render(
      <AgentPreview
        config={{
          name: "Min",
          model: "gpt-4o",
          skills: [],
          tools: [],
          mcpServers: [],
          knowledge: [],
          integrations: [],
          inputs: [],
          outputs: [],
          actions: [],
        }}
      />
    );
    expect(screen.queryByText("Mochila")).not.toBeInTheDocument();
    expect(screen.queryByText("Contrato de Fluxo")).not.toBeInTheDocument();
    expect(screen.getByText("Min")).toBeInTheDocument();
  });

  it("chama /api/agents/validate com debounce de 500 ms ao mudar a config", async () => {
    vi.useFakeTimers();
    mockPost.mockResolvedValue({ valid: true, missing: [], errors: [] });
    render(<AgentPreview config={makeConfig({ name: "A" })} />);
    // Sem debounce aplicado, a 1ª validação ainda não saiu.
    expect(mockPost).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(600);
    });
    expect(mockPost).toHaveBeenCalledTimes(1);
    expect(mockPost.mock.calls[0][0]).toBe("/api/agents/validate");
    expect(mockPost.mock.calls[0][1]).toHaveProperty("name", "A");
    vi.useRealTimers();
  });

  it("reinicia o debounce ao trocar de config (uma chamada só após 500 ms)", async () => {
    vi.useFakeTimers();
    mockPost.mockResolvedValue({ valid: true, missing: [], errors: [] });
    const { rerender } = render(<AgentPreview config={makeConfig({ name: "A" })} />);
    act(() => {
      vi.advanceTimersByTime(300);
    });
    // 300 ms depois: ainda nada (timer ainda correndo).
    expect(mockPost).not.toHaveBeenCalled();
    // Troca de config: o timer é reiniciado (de novo 500 ms).
    rerender(<AgentPreview config={makeConfig({ name: "B" })} />);
    act(() => {
      vi.advanceTimersByTime(300);
    });
    // 300 + 300 ms: sem reinício teriam saído 2 chamadas; com reinício, 1.
    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(mockPost).toHaveBeenCalledTimes(1);
    expect(mockPost.mock.calls[0][1]).toHaveProperty("name", "B");
    vi.useRealTimers();
  });

  it("não valida quando a config está vazia", () => {
    vi.useFakeTimers();
    mockPost.mockResolvedValue({ valid: true, missing: [], errors: [] });
    render(<AgentPreview config={{}} />);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(mockPost).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it('mostra "✓ pronto para salvar" quando valid=true', async () => {
    vi.useFakeTimers();
    mockPost.mockResolvedValue({ valid: true, missing: [], errors: [] });
    render(<AgentPreview config={makeConfig()} />);
    act(() => {
      vi.advanceTimersByTime(600);
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText("✓ pronto para salvar")).toBeInTheDocument();
    vi.useRealTimers();
  });

  it('mostra "Falta: nome, saídas" quando valid=false com missing', async () => {
    vi.useFakeTimers();
    mockPost.mockResolvedValue({ valid: false, missing: ["name", "outputs"], errors: [] });
    render(<AgentPreview config={makeConfig()} />);
    act(() => {
      vi.advanceTimersByTime(600);
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText("Falta: nome, saídas")).toBeInTheDocument();
    vi.useRealTimers();
  });

  it("esconde o status de validação quando o config é vazio", () => {
    mockPost.mockResolvedValue({ valid: true, missing: [], errors: [] });
    render(<AgentPreview config={{}} />);
    expect(screen.queryByText("✓ pronto para salvar")).not.toBeInTheDocument();
    expect(screen.queryByText(/^Falta:/)).not.toBeInTheDocument();
  });
});
