import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { OnboardingChecklist } from "./onboarding-checklist";

describe("OnboardingChecklist", () => {
  it("renders the title and the four items", () => {
    render(
      <OnboardingChecklist
        hasAgent={false}
        hasPipeline={false}
        hasKnowledge={false}
        hasMcp={false}
      />
    );
    expect(screen.getByText("Primeiros passos")).toBeInTheDocument();
    expect(screen.getByText("Crie um agente")).toBeInTheDocument();
    expect(screen.getByText("Crie uma pipeline")).toBeInTheDocument();
    expect(screen.getByText("Adicione uma base de conhecimento")).toBeInTheDocument();
    expect(screen.getByText("Conecte uma ferramenta (MCP)")).toBeInTheDocument();
  });

  it("marks an item when its condition is true", () => {
    render(
      <OnboardingChecklist
        hasAgent={true}
        hasPipeline={false}
        hasKnowledge={false}
        hasMcp={false}
      />
    );
    const item = screen.getByText("Crie um agente").closest("li");
    expect(item).toHaveAttribute("data-done", "true");
  });

  it("leaves items unmarked when the condition is false", () => {
    render(
      <OnboardingChecklist
        hasAgent={false}
        hasPipeline={false}
        hasKnowledge={false}
        hasMcp={false}
      />
    );
    const item = screen.getByText("Crie um agente").closest("li");
    expect(item).toHaveAttribute("data-done", "false");
  });

  it("marks every item when all conditions are true", () => {
    render(
      <OnboardingChecklist
        hasAgent={true}
        hasPipeline={true}
        hasKnowledge={true}
        hasMcp={true}
      />
    );
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(4);
    for (const item of items) {
      expect(item).toHaveAttribute("data-done", "true");
    }
  });
});
