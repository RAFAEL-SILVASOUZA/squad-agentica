import * as React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StepsList, topoOrder } from "./steps-list";
import type { Pipeline, PipelineNode, PipelineEdge, Agent } from "@/lib/types";

function makeNode(id: string, name: string, inputs: string[] = [], outputs: string[] = []): PipelineNode {
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
      inputs: inputs.map((n) => ({ name: n, type: "string", required: false })),
      outputs: outputs.map((n) => ({ name: n, type: "string", required: false })),
      actions: ["follow"],
      model: "gpt-4o",
      maxIterations: 5,
      timeout: 300,
      shellAccess: false,
    },
  };
}

function makeEdge(id: string, source: string, target: string, type: "flow" | "data" = "flow"): PipelineEdge {
  return { id, type, source, target, requiresApproval: false };
}

function makePipeline(nodes: PipelineNode[], edges: PipelineEdge[]): Pipeline {
  return {
    id: "pipe-1",
    ownerId: "user-1",
    name: "Test",
    description: "",
    status: "draft",
    entryNodeId: nodes[0]?.id ?? "",
    nodes,
    edges,
    currentCheckpoint: null,
    startedAt: null,
    completedAt: null,
    repository: null,
  };
}

const mockAgents: Agent[] = [
  {
    id: "agent-x",
    ownerId: "user-1",
    name: "Agent X",
    type: "Dev",
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
    maxIterations: 5,
    timeout: 300,
    shellAccess: false,
  },
];

describe("topoOrder", () => {
  it("ordena A→B→A e C→D: C, D primeiro e cyclic=[A,B]", () => {
    const nodes = [makeNode("A", "A"), makeNode("B", "B"), makeNode("C", "C"), makeNode("D", "D")];
    const edges = [
      makeEdge("e1", "A", "B"),
      makeEdge("e2", "B", "A"),
      makeEdge("e3", "C", "D"),
    ];
    const { order, cyclic } = topoOrder(nodes, edges);
    expect(order[0]).toBe("C");
    expect(order[1]).toBe("D");
    expect(cyclic).toEqual(["A", "B"]);
    expect(order).toEqual(["C", "D", "A", "B"]);
  });

  it("sem ciclos: ordem topologica simples", () => {
    const nodes = [makeNode("A", "A"), makeNode("B", "B"), makeNode("C", "C")];
    const edges = [makeEdge("e1", "A", "B"), makeEdge("e2", "B", "C")];
    const { order, cyclic } = topoOrder(nodes, edges);
    expect(order).toEqual(["A", "B", "C"]);
    expect(cyclic).toEqual([]);
  });

  it("sem arestas: todos na ordem original, sem cyclic", () => {
    const nodes = [makeNode("A", "A"), makeNode("B", "B")];
    const { order, cyclic } = topoOrder(nodes, []);
    expect(order).toEqual(["A", "B"]);
    expect(cyclic).toEqual([]);
  });
});

describe("StepsList", () => {
  it("mostra 'Etapas' e os nos em ordem topologica", () => {
    const nodes = [makeNode("A", "Agent A"), makeNode("B", "Agent B")];
    const edges = [makeEdge("e1", "A", "B")];
    render(<StepsList pipeline={makePipeline(nodes, edges)} agents={mockAgents} onChange={vi.fn()} />);
    expect(screen.getByText("Etapas")).toBeInTheDocument();
    expect(screen.getByTestId("step-A")).toBeInTheDocument();
    expect(screen.getByTestId("step-B")).toBeInTheDocument();
    // A aparece antes de B na ordem topologica
    const stepA = screen.getByTestId("step-A");
    const stepB = screen.getByTestId("step-B");
    expect(stepA.compareDocumentPosition(stepB) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("mostra aviso de ciclo quando ha ciclo", () => {
    const nodes = [makeNode("A", "Agent A"), makeNode("B", "Agent B")];
    const edges = [makeEdge("e1", "A", "B"), makeEdge("e2", "B", "A")];
    render(<StepsList pipeline={makePipeline(nodes, edges)} agents={mockAgents} onChange={vi.fn()} />);
    expect(screen.getByText(/Há um ciclo envolvendo: Agent A, Agent B/)).toBeInTheDocument();
  });

  it("'Adicionar agente' cria um no novo", async () => {
    const onChange = vi.fn();
    const nodes = [makeNode("A", "Agent A")];
    render(<StepsList pipeline={makePipeline(nodes, [])} agents={mockAgents} onChange={onChange} />);

    const select = screen.getByLabelText("Escolher agente para adicionar");
    await userEvent.selectOptions(select, "agent-x");
    await userEvent.click(screen.getByRole("button", { name: /adicionar agente/i }));

    expect(onChange).toHaveBeenCalled();
    const [newNodes] = onChange.mock.calls[0];
    expect(newNodes).toHaveLength(2);
    expect(newNodes[1].agentSnapshot.name).toBe("Agent X");
  });

  it("'Conectar a…' cria uma flow edge", async () => {
    const onChange = vi.fn();
    const nodes = [makeNode("A", "Agent A"), makeNode("B", "Agent B")];
    render(<StepsList pipeline={makePipeline(nodes, [])} agents={mockAgents} onChange={onChange} />);

    await userEvent.selectOptions(screen.getByLabelText("Conectar de"), "A");
    await userEvent.selectOptions(screen.getByLabelText("Conectar para"), "B");
    await userEvent.click(screen.getByRole("button", { name: /conectar a/i }));

    expect(onChange).toHaveBeenCalled();
    const [, newEdges] = onChange.mock.calls[0];
    expect(newEdges).toHaveLength(1);
    expect(newEdges[0].type).toBe("flow");
    expect(newEdges[0].source).toBe("A");
    expect(newEdges[0].target).toBe("B");
  });

  it("Remover pede confirmacao e exclui o no", async () => {
    const onChange = vi.fn();
    const nodes = [makeNode("A", "Agent A"), makeNode("B", "Agent B")];
    render(<StepsList pipeline={makePipeline(nodes, [])} agents={mockAgents} onChange={onChange} />);

    await userEvent.click(screen.getByRole("button", { name: /remover agent a/i }));
    expect(screen.getByText("Excluir esta etapa?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /confirmar/i }));

    expect(onChange).toHaveBeenCalled();
    const [newNodes] = onChange.mock.calls[0];
    expect(newNodes).toHaveLength(1);
    expect(newNodes[0].id).toBe("B");
  });

  it("mostra estado vazio quando nao ha nos", () => {
    render(<StepsList pipeline={makePipeline([], [])} agents={mockAgents} onChange={vi.fn()} />);
    expect(screen.getByText(/Nenhuma etapa/)).toBeInTheDocument();
  });
});
