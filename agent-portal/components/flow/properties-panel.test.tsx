import * as React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PropertiesPanel } from "./properties-panel";
import type { ValidationError } from "./validation";
import type { Pipeline, PipelineNode, PipelineEdge } from "@/lib/types";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

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

function makePipeline(nodes: PipelineNode[], edges: PipelineEdge[]): Pipeline {
  return {
    id: "pipe-1",
    ownerId: "user-1",
    name: "Meu Pipeline",
    description: "Pipeline de teste",
    status: "draft",
    entryNodeId: nodes[0]?.id ?? "",
    nodes,
    edges,
    currentCheckpoint: null,
    startedAt: null,
    completedAt: null,
    repository: { integrationId: "int-1", fullName: "org/repo", baseBranch: "main" },
  };
}

const baseProps = {
  onChangeNode: vi.fn(),
  onChangeEdge: vi.fn(),
  onDeleteNode: vi.fn(),
  onDeleteEdge: vi.fn(),
};

describe("PropertiesPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("sem selecao: mostra 'Pipeline' com nome, descricao e repositório", () => {
    const nodes = [makeNode("n1", "Redator", [], ["result"])];
    render(
      <PropertiesPanel
        pipeline={makePipeline(nodes, [])}
        selection={null}
        {...baseProps}
      />
    );
    expect(screen.getByText("Pipeline")).toBeInTheDocument();
    expect(screen.getByText("Meu Pipeline")).toBeInTheDocument();
    expect(screen.getByText("Pipeline de teste")).toBeInTheDocument();
    expect(screen.getByText("org/repo")).toBeInTheDocument();
  });

  it("sem selecao: erro de validacao clicavel", () => {
    const nodes = [makeNode("n1", "Redator")];
    const errors: ValidationError[] = [
      { rule: 8, message: '"Redator" é um nó órfão', nodeId: "n1" },
    ];
    render(
      <PropertiesPanel
        pipeline={makePipeline(nodes, [])}
        selection={null}
        errors={errors}
        {...baseProps}
      />
    );
    expect(screen.getByText(/é um nó órfão/)).toBeInTheDocument();
  });

  it("no selecionado: mostra 'Entradas' com select por entrada", () => {
    const nodes = [
      makeNode("redator", "Redator", [], ["result"]),
      makeNode("revisor", "Revisor", ["text"], []),
    ];
    render(
      <PropertiesPanel
        pipeline={makePipeline(nodes, [])}
        selection={{ nodeId: "revisor" }}
        {...baseProps}
      />
    );
    expect(screen.getByText("Entradas")).toBeInTheDocument();
    expect(screen.getByLabelText("text")).toBeInTheDocument();
  });

  it("no selecionado: escolher 'Saida result de Redator' cria data edge", async () => {
    const onChangeEdge = vi.fn();
    const nodes = [
      makeNode("redator", "Redator", [], ["result"]),
      makeNode("revisor", "Revisor", ["text"], []),
    ];
    render(
      <PropertiesPanel
        pipeline={makePipeline(nodes, [])}
        selection={{ nodeId: "revisor" }}
        onChangeNode={vi.fn()}
        onChangeEdge={onChangeEdge}
        onDeleteNode={vi.fn()}
        onDeleteEdge={vi.fn()}
      />
    );
    const select = screen.getByLabelText("text");
    await userEvent.selectOptions(select, "redator:result");

    expect(onChangeEdge).toHaveBeenCalled();
    const edge = onChangeEdge.mock.calls[0][0];
    expect(edge.type).toBe("data");
    expect(edge.source).toBe("redator");
    expect(edge.target).toBe("revisor");
    expect(edge.dataMapping).toEqual({ sourceOutput: "result", targetInput: "text" });
  });

  it("no selecionado: 'Excluir nó' pede confirmacao", async () => {
    const onDeleteNode = vi.fn();
    const nodes = [makeNode("n1", "Redator")];
    render(
      <PropertiesPanel
        pipeline={makePipeline(nodes, [])}
        selection={{ nodeId: "n1" }}
        onChangeNode={vi.fn()}
        onChangeEdge={vi.fn()}
        onDeleteNode={onDeleteNode}
        onDeleteEdge={vi.fn()}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: /excluir nó/i }));
    expect(screen.getByText("Excluir este nó?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /confirmar/i }));
    expect(onDeleteNode).toHaveBeenCalledWith("n1");
  });

  it("aresta selecionada: mostra tipo, condicao e aprovacao", () => {
    const nodes = [makeNode("n1", "Redator"), makeNode("n2", "Revisor")];
    const edges: PipelineEdge[] = [
      {
        id: "e1",
        type: "flow",
        source: "n1",
        target: "n2",
        requiresApproval: true,
        approvalChannel: "email",
        approvalMessage: "Aprovar?",
      },
    ];
    render(
      <PropertiesPanel
        pipeline={makePipeline(nodes, edges)}
        selection={{ edgeId: "e1" }}
        {...baseProps}
      />
    );
    // Tipo da aresta (EdgePanelContent renderiza o select "Tipo")
    expect(screen.getByLabelText(/tipo/i)).toBeInTheDocument();
    // Aprovacao
    expect(screen.getByText(/requer aprovação/i)).toBeInTheDocument();
  });
});
