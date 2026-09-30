import * as React from "react";
import { describe, it, expect } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { LogsTab, type LogEntry } from "./logs-tab";

const logs: LogEntry[] = [
  { id: "1", nodeId: "a", level: "info", message: "redator começou", at: "2026-01-01T10:00:00Z" },
  { id: "2", nodeId: "b", level: "info", message: "revisor começou", at: "2026-01-01T10:00:01Z" },
  { id: "3", nodeId: "b", level: "error", message: "revisor quebrou", at: "2026-01-01T10:00:02Z" },
  { id: "4", nodeId: "a", level: "warn", message: "redator avisou", at: "2026-01-01T10:00:03Z" },
];
const agents = [
  { nodeId: "a", name: "Redator" },
  { nodeId: "b", name: "Revisor" },
];

describe("LogsTab", () => {
  it("filters by agent and by level", () => {
    render(<LogsTab logs={logs} agents={agents} />);
    const log = screen.getByRole("log");
    expect(within(log).getAllByText(/começou|quebrou|avisou/)).toHaveLength(4);
    // A linha mostra o nome do agente, não o id do nó.
    expect(within(log).getAllByText("Redator")).toHaveLength(2);

    fireEvent.change(screen.getByLabelText("Filtrar por agente"), { target: { value: "b" } });
    expect(within(log).queryByText("redator começou")).not.toBeInTheDocument();
    expect(within(log).getByText("revisor começou")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Filtrar por agente"), { target: { value: "all" } });
    fireEvent.change(screen.getByLabelText("Filtrar por nível"), { target: { value: "error" } });
    expect(within(log).getAllByText(/começou|quebrou|avisou/)).toHaveLength(1);
    expect(within(log).getByText("revisor quebrou")).toBeInTheDocument();
  });

  it("shows the empty messages", () => {
    const { rerender } = render(<LogsTab logs={[]} agents={agents} />);
    expect(screen.getByText("Aguardando logs da execução…")).toBeInTheDocument();
    rerender(<LogsTab logs={logs.slice(0, 1)} agents={agents} />);
    fireEvent.change(screen.getByLabelText("Filtrar por nível"), { target: { value: "error" } });
    expect(screen.getByText("Nenhum log corresponde ao filtro.")).toBeInTheDocument();
  });

  it("renders logs as a numbered list with monospace font", () => {
    render(<LogsTab logs={logs} agents={agents} />);
    const log = screen.getByRole("log");
    // Os logs são renderizados como <ol> (numeração)
    const ol = log.querySelector("ol");
    expect(ol).not.toBeNull();
    const items = ol!.querySelectorAll("li");
    expect(items).toHaveLength(4);
    // Fonte monospace
    expect(log.style.fontFamily).toContain("mono");
  });
});
