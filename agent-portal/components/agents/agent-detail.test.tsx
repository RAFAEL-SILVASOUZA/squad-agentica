import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { AgentDetail } from "./agent-detail";
import { ToastProvider } from "@/components/ui/toast";
import type { Agent, Skill, CustomTool, MCPServer, KnowledgeBase } from "@/lib/types";

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

describe("AgentDetail", () => {
  it("pre-fills fields from an existing agent", () => {
    renderDetail({ agent: makeAgent() });
    expect(
      screen.getByDisplayValue("Backend Developer")
    ).toBeInTheDocument();
    expect(screen.getByDisplayValue("Dev de APIs REST.")).toBeInTheDocument();
    expect(screen.getByDisplayValue("gpt-4o")).toBeInTheDocument();
    expect(screen.getByDisplayValue("5")).toBeInTheDocument();
    expect(screen.getByDisplayValue("300")).toBeInTheDocument();
    expect(screen.getByDisplayValue("plano_aprovado")).toBeInTheDocument();
    expect(screen.getByDisplayValue("code_pronto")).toBeInTheDocument();
  });

  it("requires a name before saving", async () => {
    const { onSave } = renderDetail({ agent: makeAgent({ name: "" }) });
    fireEvent.click(screen.getByRole("button", { name: /salvar/i }));
    await waitFor(() => {
      expect(screen.getByText("Informe um nome para o agente.")).toBeInTheDocument();
    });
    expect(onSave).not.toHaveBeenCalled();
  });

  it("saves with the edited name and contract", async () => {
    const { onSave } = renderDetail({ agent: makeAgent() });
    const nameInput = screen.getByDisplayValue("Backend Developer");
    fireEvent.change(nameInput, { target: { value: "Novo Nome" } });
    fireEvent.click(screen.getByRole("button", { name: /salvar/i }));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalled();
    });
    const payload = onSave.mock.calls[0][0];
    expect(payload.name).toBe("Novo Nome");
    expect(payload.inputs).toEqual([
      { name: "plano_aprovado", type: "object", required: true },
    ]);
    expect(payload.actions).toEqual(["follow", "finalize"]);
  });

  it("toggles an action", async () => {
    const { onSave } = renderDetail({ agent: makeAgent() });
    // "return" não está ativo no agente; clique para ativar.
    fireEvent.click(screen.getByRole("button", { name: "Devolver" }));
    fireEvent.click(screen.getByRole("button", { name: /salvar/i }));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalled();
    });
    const payload = onSave.mock.calls[0][0];
    expect(payload.actions).toContain("return");
  });

  it("adds a skill from the selector", async () => {
    const { onSave } = renderDetail({ agent: makeAgent({ skills: [] }) });
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

  it("adds an integration from the selector", async () => {
    const { onSave } = renderDetail({ agent: makeAgent({ integrations: [] }) });
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

  it("toggles shellAccess", async () => {
    const { onSave } = renderDetail({ agent: makeAgent({ shellAccess: false }) });
    fireEvent.click(screen.getByRole("switch", { name: "Acesso a shell" }));
    fireEvent.click(screen.getByRole("button", { name: /salvar/i }));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalled();
    });
    const payload = onSave.mock.calls[0][0];
    expect(payload.shellAccess).toBe(true);
  });

  it("shows empty backpack hints when no options", async () => {
    render(
      <ToastProvider>
        <AgentDetail
          options={{ skills: [], tools: [], mcpServers: [], knowledge: [] }}
          onSave={vi.fn()}
        />
      </ToastProvider>
    );
    expect(screen.getByText("Nenhuma skill cadastrada")).toBeInTheDocument();
    expect(screen.getByText("Nenhuma tool cadastrada")).toBeInTheDocument();
    expect(screen.getByText("Nenhum servidor cadastrado")).toBeInTheDocument();
    expect(screen.getByText("Nenhuma base cadastrada")).toBeInTheDocument();
  });
});
