import { describe, it, expect, vi, beforeEach } from "vitest";
import { render as rtlRender, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { screen } from "@testing-library/react";
import { EdgePanel } from "./EdgePanel";
import type { PipelineEdge, PipelineNode } from "@/lib/types";

function makeNode(
  id: string,
  name: string,
  inputs: { name: string; type: string; required?: boolean }[],
  outputs: { name: string; type: string }[]
): PipelineNode {
  return {
    id,
    agentId: `agent-${id}`,
    position: { x: 0, y: 0 },
    label: name,
    agentSnapshot: {
      agentId: `agent-${id}`,
      version: 1,
      name,
      description: "",
      prompt: "",
      strategy: "",
      skills: [],
      tools: [],
      mcpServers: [],
      knowledge: [],
      integrations: [],
      inputs: inputs.map((p) => ({ name: p.name, type: p.type, required: p.required ?? false })),
      outputs: outputs.map((p) => ({ name: p.name, type: p.type, required: false })),
      actions: ["follow", "return", "finalize"],
      model: "gpt-4o",
      maxIterations: 5,
      timeout: 300,
      shellAccess: false,
    },
  };
}

const nodes = [
  makeNode("n1", "Planner", [], [{ name: "plan", type: "string" }, { name: "plan_json", type: "object" }]),
  makeNode("n2", "Coder", [{ name: "task", type: "string", required: true }, { name: "feedback", type: "string" }], [{ name: "code", type: "string" }]),
];

function makeEdge(overrides: Partial<PipelineEdge> = {}): PipelineEdge {
  return {
    id: "edge-1",
    type: "flow",
    source: "n1",
    target: "n2",
    requiresApproval: false,
    ...overrides,
  };
}

describe("EdgePanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders source -> target title and type select", () => {
    rtlRender(
      <EdgePanel edge={makeEdge()} nodes={nodes} onChange={vi.fn()} onClose={vi.fn()} />
    );
    expect(screen.getByText(/Planner/)).toBeInTheDocument();
    expect(screen.getByText(/Coder/)).toBeInTheDocument();
    expect(screen.getByLabelText("Tipo")).toBeInTheDocument();
  });

  it("shows dataMapping selects for data edges and updates on change", async () => {
    const onChange = vi.fn();
    rtlRender(
      <EdgePanel
        edge={makeEdge({ type: "data" })}
        nodes={nodes}
        onChange={onChange}
        onClose={vi.fn()}
      />
    );

    const sourceOut = screen.getByLabelText("Output do source") as HTMLSelectElement;
    const targetIn = screen.getByLabelText("Input do target") as HTMLSelectElement;
    expect(sourceOut).toBeInTheDocument();
    expect(targetIn).toBeInTheDocument();

    await userEvent.selectOptions(sourceOut, "plan");
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({
        id: "edge-1",
        type: "data",
        dataMapping: { sourceOutput: "plan", targetInput: "" },
      })
    );

    await userEvent.selectOptions(targetIn, "task");
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({
        dataMapping: { sourceOutput: "plan", targetInput: "task" },
      })
    );
  });

  it("shows a type mismatch error when mapping ports of different types", () => {
    rtlRender(
      <EdgePanel
        edge={makeEdge({
          type: "data",
          dataMapping: { sourceOutput: "plan_json", targetInput: "task" },
        })}
        nodes={nodes}
        onChange={vi.fn()}
        onClose={vi.fn()}
      />
    );
    expect(
      screen.getAllByRole("alert").find((el) => /tipo incompatível/.test(el.textContent ?? ""))
    ).toBeTruthy();
  });

  it("does not show type error when mapping is coherent", () => {
    rtlRender(
      <EdgePanel
        edge={makeEdge({
          type: "data",
          dataMapping: { sourceOutput: "plan", targetInput: "task" },
        })}
        nodes={nodes}
        onChange={vi.fn()}
        onClose={vi.fn()}
      />
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("reports an error when sourceOutput does not exist on the source agent", () => {
    rtlRender(
      <EdgePanel
        edge={makeEdge({
          type: "data",
          dataMapping: { sourceOutput: "missing", targetInput: "task" },
        })}
        nodes={nodes}
        onChange={vi.fn()}
        onClose={vi.fn()}
      />
    );
    expect(
      screen.getAllByRole("alert").find((el) => /não existe nos outputs/.test(el.textContent ?? ""))
    ).toBeTruthy();
  });

  it("configures condition on a flow edge (operator + action)", async () => {
    const onChange = vi.fn();
    rtlRender(
      <EdgePanel
        edge={makeEdge({
          condition: { field: "action", operator: "eq", value: "follow" },
        })}
        nodes={nodes}
        onChange={onChange}
        onClose={vi.fn()}
      />
    );

    const operator = screen.getByLabelText("Operador") as HTMLSelectElement;
    await userEvent.selectOptions(operator, "neq");
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({
        condition: { field: "action", operator: "neq", value: "follow" },
      })
    );

    const action = screen.getByLabelText("Ação") as HTMLSelectElement;
    await userEvent.selectOptions(action, "return");
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({
        condition: { field: "action", operator: "neq", value: "return" },
      })
    );
  });

  it("clears the condition when choosing unconditional", async () => {
    const onChange = vi.fn();
    rtlRender(
      <EdgePanel
        edge={makeEdge({
          condition: { field: "action", operator: "eq", value: "follow" },
        })}
        nodes={nodes}
        onChange={onChange}
        onClose={vi.fn()}
      />
    );
    const checkbox = screen.getByRole("checkbox", { name: "Definir condição de ação" });
    expect(checkbox).toBeChecked();
    await userEvent.click(checkbox);
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ condition: undefined })
    );

    // E o inverso: sem condicao, ligar o checkbox cria uma condicao padrao
    cleanup();
    const onChange2 = vi.fn();
    rtlRender(
      <EdgePanel edge={makeEdge()} nodes={nodes} onChange={onChange2} onClose={vi.fn()} />
    );
    const cb2 = screen.getByRole("checkbox", { name: "Definir condição de ação" });
    expect(cb2).not.toBeChecked();
    await userEvent.click(cb2);
    expect(onChange2).toHaveBeenLastCalledWith(
      expect.objectContaining({
        condition: { field: "action", operator: "eq", value: "follow" },
      })
    );
  });

  it("toggles requiresApproval and reveals channel + message fields", async () => {
    const onChange = vi.fn();
    const { rerender } = rtlRender(
      <EdgePanel edge={makeEdge()} nodes={nodes} onChange={onChange} onClose={vi.fn()} />
    );

    const toggle = screen.getByRole("switch", { name: "Requer aprovação" });
    expect(toggle).toHaveAttribute("aria-checked", "false");
    await userEvent.click(toggle);
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({
        requiresApproval: true,
        approvalChannel: "in-app",
        approvalMessage: "",
      })
    );

    // Re-render with approval enabled to see the fields
    rerender(
      <EdgePanel
        edge={makeEdge({
          requiresApproval: true,
          approvalChannel: "in-app",
          approvalMessage: "",
        })}
        nodes={nodes}
        onChange={onChange}
        onClose={vi.fn()}
      />
    );
    const channel = screen.getByLabelText("Canal de notificação") as HTMLSelectElement;
    await userEvent.selectOptions(channel, "email");
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ approvalChannel: "email" })
    );
  });

  it("shows graph validation errors passed via props", () => {
    rtlRender(
      <EdgePanel
        edge={makeEdge()}
        nodes={nodes}
        onChange={vi.fn()}
        onClose={vi.fn()}
        errors={["flow edges duplicadas entre n1 e n2"]}
      />
    );
    expect(
      screen.getAllByRole("alert").find((el) => /flow edges duplicadas/.test(el.textContent ?? ""))
    ).toBeTruthy();
  });

  it("closes via the close button", async () => {
    const onClose = vi.fn();
    rtlRender(
      <EdgePanel edge={makeEdge()} nodes={nodes} onChange={vi.fn()} onClose={onClose} />
    );
    await userEvent.click(screen.getByRole("button", { name: "Fechar painel da aresta" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("shows the reject target info (V1: compiler-derived) when approval is on", () => {
    rtlRender(
      <EdgePanel
        edge={makeEdge({ requiresApproval: true, approvalChannel: "in-app" })}
        nodes={nodes}
        onChange={vi.fn()}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByText(/Alvo de rejeição/)).toBeInTheDocument();
  });
});
