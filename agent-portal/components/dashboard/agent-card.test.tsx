import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { AgentCard } from "./agent-card";
import type { Agent } from "@/lib/types";

function makeAgent(overrides: Partial<Agent> = {}): Agent {
  return {
    id: "agent-1",
    ownerId: "owner-1",
    name: "Planner",
    type: "Planner",
    description: "",
    prompt: "",
    strategy: "",
    skills: [],
    tools: [],
    mcpServers: [],
    knowledge: [],
    integrations: [],
    inputs: [],
    outputs: [],
    actions: [],
    model: "gpt-4o",
    maxIterations: 10,
    timeout: 300,
    shellAccess: false,
    ...overrides,
  };
}

describe("AgentCard", () => {
  it("renders agent name and type", () => {
    render(<AgentCard agent={makeAgent({ name: "Planner", type: "Coordinador" })} />);
    expect(screen.getByText("Planner")).toBeInTheDocument();
    expect(screen.getByText("Coordinador")).toBeInTheDocument();
  });

  it("links to /agents/{id}", () => {
    render(<AgentCard agent={makeAgent({ id: "abc" })} />);
    const link = screen.getByRole("link", { name: /abrir agente planner/i });
    expect(link).toHaveAttribute("href", "/agents/abc");
  });

  it("shows running status label", () => {
    render(<AgentCard agent={makeAgent()} status="running" />);
    expect(screen.getByText("Executando")).toBeInTheDocument();
  });

  it("shows idle status label by default", () => {
    render(<AgentCard agent={makeAgent()} />);
    expect(screen.getByText("Ocioso")).toBeInTheDocument();
  });

  it("renders integration platform tags", () => {
    render(
      <AgentCard
        agent={makeAgent({
          integrations: [
            { platform: "github", config: {} },
            { platform: "azure", config: {} },
          ],
        })}
      />
    );
    expect(screen.getByText("github")).toBeInTheDocument();
    expect(screen.getByText("azure")).toBeInTheDocument();
  });

  it("renders skill tags", () => {
    render(
      <AgentCard
        agent={makeAgent({
          skills: [{ skillId: "code-review", config: {} }],
        })}
      />
    );
    expect(screen.getByText("code-review")).toBeInTheDocument();
  });

  it("caps tags at 3", () => {
    render(
      <AgentCard
        agent={makeAgent({
          integrations: [
            { platform: "github", config: {} },
            { platform: "azure", config: {} },
            { platform: "gitlab", config: {} },
            { platform: "email", config: {} },
          ],
        })}
      />
    );
    expect(screen.getByText("github")).toBeInTheDocument();
    expect(screen.getByText("azure")).toBeInTheDocument();
    expect(screen.getByText("gitlab")).toBeInTheDocument();
    expect(screen.queryByText("email")).not.toBeInTheDocument();
  });

  it("renders no tags when agent has none", () => {
    render(<AgentCard agent={makeAgent()} />);
    expect(screen.queryByText("github")).not.toBeInTheDocument();
  });
});
