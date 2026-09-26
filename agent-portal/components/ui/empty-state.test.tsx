import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { EmptyState } from "./empty-state";
import { Bot } from "lucide-react";

describe("EmptyState", () => {
  it("renders title", () => {
    render(<EmptyState title="Nenhum agente" />);
    expect(screen.getByText("Nenhum agente")).toBeInTheDocument();
  });

  it("renders description when provided", () => {
    render(
      <EmptyState title="Nenhum agente" description="Crie seu primeiro agente" />
    );
    expect(screen.getByText("Crie seu primeiro agente")).toBeInTheDocument();
  });

  it("renders icon when provided", () => {
    render(<EmptyState title="Nenhum agente" icon={Bot} />);
    const svg = document.querySelector("svg");
    expect(svg).toBeInTheDocument();
  });

  it("renders action when provided", () => {
    render(
      <EmptyState
        title="Nenhum agente"
        action={<button>Criar agente</button>}
      />
    );
    expect(screen.getByRole("button", { name: "Criar agente" })).toBeInTheDocument();
  });

  it("does not render description when not provided", () => {
    render(<EmptyState title="Nenhum agente" />);
    expect(screen.queryByText("Crie seu primeiro agente")).not.toBeInTheDocument();
  });
});
