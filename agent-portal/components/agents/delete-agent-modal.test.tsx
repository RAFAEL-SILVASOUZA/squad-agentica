import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { DeleteAgentModal } from "./delete-agent-modal";

describe("DeleteAgentModal", () => {
  it("does not render when closed", () => {
    render(
      <DeleteAgentModal
        open={false}
        agentName="Dev"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(screen.queryByText("Excluir agente")).not.toBeInTheDocument();
  });

  it("shows the agent name and confirms on click", () => {
    const onConfirm = vi.fn();
    render(
      <DeleteAgentModal
        open
        agentName="Backend Developer"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />
    );
    expect(screen.getByText("Excluir agente")).toBeInTheDocument();
    expect(screen.getByText("Backend Developer")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /excluir/i }));
    expect(onConfirm).toHaveBeenCalled();
  });

  it("cancels on click", () => {
    const onCancel = vi.fn();
    render(
      <DeleteAgentModal
        open
        agentName="Dev"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /cancelar/i }));
    expect(onCancel).toHaveBeenCalled();
  });

  it("disables buttons while deleting", () => {
    render(
      <DeleteAgentModal
        open
        agentName="Dev"
        deleting
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(screen.getByRole("button", { name: /cancelar/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /excluir/i })).toBeDisabled();
  });
});
