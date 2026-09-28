import * as React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, within, fireEvent } from "@testing-library/react";
import { ResultsTab } from "./results-tab";

describe("ResultsTab", () => {
  it("shows each agent output as rendered markdown in order, full width", () => {
    render(
      <ResultsTab
        steps={[
          { nodeId: "a", name: "Redator", status: "completed", output: { especificacao: "# Spec\n\n- RF-001" } },
          { nodeId: "b", name: "Revisor", status: "running", output: undefined },
        ]}
      />
    );
    const sections = screen.getAllByRole("region");
    expect(sections[0]).toHaveAccessibleName("Redator");
    expect(within(sections[0]).getByRole("heading", { name: "Spec" })).toBeInTheDocument();
    expect(within(sections[1]).getByText(/Em execução/)).toBeInTheDocument();
  });

  it("copies an output", async () => {
    const writeText = vi.fn();
    Object.assign(navigator, { clipboard: { writeText } });
    render(
      <ResultsTab steps={[{ nodeId: "a", name: "Redator", status: "completed", output: { especificacao: "texto" } }]} />
    );
    fireEvent.click(screen.getByRole("button", { name: "Copiar especificacao" }));
    expect(writeText).toHaveBeenCalledWith("texto");
  });

  it("hides the internal _action port, shows non-text values as JSON and plain string outputs", () => {
    render(
      <ResultsTab
        steps={[
          { nodeId: "a", name: "Redator", status: "completed", output: { _action: "follow", itens: [1, 2] } },
          { nodeId: "b", name: "Revisor", status: "completed", output: "**ok**" },
          { nodeId: "c", name: "Testador", status: "pending", output: undefined },
        ]}
      />
    );
    const [a, b, c] = screen.getAllByRole("region");
    expect(within(a).queryByText("_action")).not.toBeInTheDocument();
    expect(within(a).getByText(/\[\s*1,\s*2\s*\]/)).toBeInTheDocument();
    expect(within(b).getByText("ok").tagName).toBe("STRONG");
    expect(within(c).getByText(/Aguardando/)).toBeInTheDocument();
  });

  it("collapses and expands a result section; focusing expands a collapsed one", () => {
    Element.prototype.scrollIntoView = vi.fn();
    const steps = [
      { nodeId: "a", name: "Redator", status: "completed" as const, output: "texto do redator" },
      { nodeId: "b", name: "Revisor", status: "completed" as const, output: "texto do revisor" },
    ];
    const { rerender } = render(<ResultsTab steps={steps} />);
    const toggle = screen.getByRole("button", { name: "Recolher Redator" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(document.getElementById(toggle.getAttribute("aria-controls")!)).toHaveTextContent("texto do redator");

    fireEvent.click(toggle);
    expect(screen.queryByText("texto do redator")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Expandir Redator" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("texto do revisor")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Expandir Redator" }));
    expect(screen.getByText("texto do redator")).toBeInTheDocument();

    // Recolhe de novo e foca pela faixa de etapas: a seção volta a abrir.
    fireEvent.click(screen.getByRole("button", { name: "Recolher Redator" }));
    rerender(<ResultsTab steps={steps} focusNodeId="a" focusKey={1} />);
    expect(screen.getByText("texto do redator")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Recolher Redator" })).toBeInTheDocument();
  });

  it("scrolls the focused agent into view", () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    render(
      <ResultsTab
        steps={[
          { nodeId: "a", name: "Redator", status: "completed", output: "x" },
          { nodeId: "b", name: "Revisor", status: "completed", output: "y" },
        ]}
        focusNodeId="b"
      />
    );
    expect(scrollIntoView).toHaveBeenCalled();
    expect(scrollIntoView.mock.contexts[0]).toBe(screen.getByRole("region", { name: "Revisor" }));
  });
});
