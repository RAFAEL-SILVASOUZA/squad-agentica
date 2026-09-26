import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { AgentPreview } from "./agent-preview";
import type { Agent } from "@/lib/types";

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

  it("renders backpack chips", () => {
    render(<AgentPreview config={makeConfig()} />);
    expect(screen.getByText("code-gen")).toBeInTheDocument();
    expect(screen.getByText("consultar_jira")).toBeInTheDocument();
    expect(screen.getByText("postgres-readonly")).toBeInTheDocument();
    expect(screen.getByText("docs-projeto")).toBeInTheDocument();
    expect(screen.getByText("github")).toBeInTheDocument();
  });

  it("hides empty sections", () => {
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
});
