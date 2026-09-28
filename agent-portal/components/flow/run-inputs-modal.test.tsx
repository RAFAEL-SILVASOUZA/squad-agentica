import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { RunInputsModal } from "./run-inputs-modal";

const inputs = [
  { name: "ideia", type: "document", required: true },
  { name: "contexto", type: "document", required: false },
];

describe("RunInputsModal", () => {
  it("blocks submit until required inputs are filled", () => {
    const onSubmit = vi.fn();
    render(
      <RunInputsModal open agentName="Redator" inputs={inputs} onCancel={() => {}} onSubmit={onSubmit} />
    );
    fireEvent.click(screen.getByRole("button", { name: /Executar/i }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("ideia");
  });

  it("submits only the filled values, trimmed", () => {
    const onSubmit = vi.fn();
    render(
      <RunInputsModal open agentName="Redator" inputs={inputs} onCancel={() => {}} onSubmit={onSubmit} />
    );
    fireEvent.change(screen.getByLabelText("ideia *"), { target: { value: "  app de tarefas  " } });
    fireEvent.click(screen.getByRole("button", { name: /Executar/i }));
    expect(onSubmit).toHaveBeenCalledWith({ ideia: "app de tarefas" });
  });
});
