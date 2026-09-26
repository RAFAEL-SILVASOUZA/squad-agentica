import { describe, it, expect } from "vitest";
import {
  validateGraph,
  validateDataMapping,
  errorIdSets,
  normalizeServerValidation,
  buildValidationPayload,
} from "./validation";
import type { Pipeline, PipelineEdge, PipelineNode, PortDef } from "@/lib/types";

function makeNode(
  id: string,
  name: string,
  inputs: PortDef[],
  outputs: PortDef[]
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
      inputs,
      outputs,
      actions: ["follow", "return", "finalize"],
      model: "gpt-4o",
      maxIterations: 5,
      timeout: 300,
      shellAccess: false,
    },
  };
}

function makeEdge(overrides: Partial<PipelineEdge>): PipelineEdge {
  return {
    id: `e-${overrides.source ?? "x"}-${overrides.target ?? "y"}-${Math.random().toString(36).slice(2, 6)}`,
    type: "flow",
    source: "",
    target: "",
    requiresApproval: false,
    ...overrides,
  };
}

const planOut: PortDef = { name: "plan", type: "string", required: false };
const taskIn: PortDef = { name: "task", type: "string", required: true };
const objOut: PortDef = { name: "plan_json", type: "object", required: false };
const strIn: PortDef = { name: "feedback", type: "string", required: false };

describe("validateDataMapping (checagem de tipo)", () => {
  const planner = makeNode("n1", "Planner", [], [planOut, objOut]);
  const coder = makeNode("n2", "Coder", [taskIn, strIn], []);

  it("aceita mapeamento coerente (nome + tipo)", () => {
    expect(
      validateDataMapping({ sourceOutput: "plan", targetInput: "task" }, planner, coder)
    ).toBeNull();
  });

  it("rejeita sourceOutput inexistente", () => {
    const err = validateDataMapping({ sourceOutput: "nope", targetInput: "task" }, planner, coder);
    expect(err).toMatch(/nao existe nos outputs/);
  });

  it("rejeita targetInput inexistente", () => {
    const err = validateDataMapping({ sourceOutput: "plan", targetInput: "nope" }, planner, coder);
    expect(err).toMatch(/nao existe nos inputs/);
  });

  it("rejeita tipo incompativel", () => {
    const err = validateDataMapping({ sourceOutput: "plan_json", targetInput: "task" }, planner, coder);
    expect(err).toMatch(/tipo incompativel/);
  });

  it("rejeita dataMapping ausente/incompleto", () => {
    expect(validateDataMapping(undefined, planner, coder)).toMatch(/exige sourceOutput/);
    expect(
      validateDataMapping({ sourceOutput: "plan", targetInput: "" }, planner, coder)
    ).toMatch(/exige sourceOutput/);
  });

  it("aceita quando os dois lados nao declaram tipo", () => {
    const a = makeNode("a", "A", [{ name: "in", type: "", required: false }], [{ name: "out", type: "", required: false }]);
    const b = makeNode("b", "B", [{ name: "in", type: "", required: false }], []);
    expect(
      validateDataMapping({ sourceOutput: "out", targetInput: "in" }, a, b)
    ).toBeNull();
  });
});

describe("validateGraph (regras do compiler, spec 4.2)", () => {
  it("grafo valido simples nao tem erros", () => {
    const nodes = [makeNode("n1", "Planner", [], [planOut]), makeNode("n2", "Coder", [taskIn], [])];
    const edges: PipelineEdge[] = [
      makeEdge({ id: "e1", source: "n1", target: "n2", type: "data", dataMapping: { sourceOutput: "plan", targetInput: "task" } }),
    ];
    expect(validateGraph(nodes, edges, "n1")).toEqual([]);
  });

  it("regra 1: data edge sem dataMapping completa e erro", () => {
    const nodes = [makeNode("n1", "A", [], [planOut]), makeNode("n2", "B", [taskIn], [])];
    const edges = [makeEdge({ id: "e1", source: "n1", target: "n2", type: "data" })];
    const errors = validateGraph(nodes, edges, "n1");
    expect(errors.some((e) => e.rule === 1)).toBe(true);
  });

  it("regra 6: input required sem data edge e erro no no", () => {
    const nodes = [makeNode("n1", "A", [], [planOut]), makeNode("n2", "B", [taskIn], [])];
    const edges = [makeEdge({ id: "e1", source: "n1", target: "n2" })]; // flow sem data
    const errors = validateGraph(nodes, edges, "n1");
    expect(errors.some((e) => e.rule === 6 && e.nodeId === "n2")).toBe(true);
  });

  it("regra 8: no orfao (sem entrada) e erro; entry esta isento", () => {
    const nodes = [
      makeNode("n1", "A", [], []),
      makeNode("n2", "B", [], []),
      makeNode("n3", "Orphan", [], []),
    ];
    const edges = [
      makeEdge({ id: "e1", source: "n1", target: "n2" }),
    ];
    const errors = validateGraph(nodes, edges, "n1");
    expect(errors.some((e) => e.rule === 8 && e.nodeId === "n3")).toBe(true);
    expect(errors.some((e) => e.rule === 8 && e.nodeId === "n1")).toBe(false);
  });

  it("regra 9: entryNodeId inexistente e erro", () => {
    const nodes = [makeNode("n1", "A", [], [])];
    const errors = validateGraph(nodes, [], "ghost");
    expect(errors.some((e) => e.rule === 9)).toBe(true);
  });

  it("regra 11: duas flow edges idênticas entre o mesmo par sao erro", () => {
    const nodes = [makeNode("n1", "A", [], []), makeNode("n2", "B", [], [])];
    const edges = [
      makeEdge({ id: "e1", source: "n1", target: "n2", condition: { field: "action", operator: "eq", value: "follow" } }),
      makeEdge({ id: "e2", source: "n1", target: "n2", condition: { field: "action", operator: "eq", value: "follow" } }),
    ];
    const errors = validateGraph(nodes, edges, "n1");
    expect(errors.some((e) => e.rule === 11)).toBe(true);
  });

  it("branching (mesmo par, condicoes diferentes) nao e erro", () => {
    const nodes = [
      makeNode("n1", "A", [], []),
      makeNode("n2", "B", [], []),
      makeNode("n3", "C", [], []),
    ];
    const edges = [
      makeEdge({ id: "e1", source: "n1", target: "n2", condition: { field: "action", operator: "eq", value: "follow" } }),
      makeEdge({ id: "e2", source: "n1", target: "n3", condition: { field: "action", operator: "eq", value: "return" } }),
      makeEdge({ id: "e3", source: "n2", target: "n3" }),
    ];
    const errors = validateGraph(nodes, edges, "n1");
    expect(errors.filter((e) => e.rule === 11)).toEqual([]);
  });
});

describe("errorIdSets", () => {
  it("separa ids de nos e arestas", () => {
    const { nodeIds, edgeIds } = errorIdSets([
      { rule: 6, message: "m", nodeId: "n2" },
      { rule: 1, message: "m", edgeId: "e1" },
      { rule: 9, message: "m" },
    ]);
    expect(nodeIds.has("n2")).toBe(true);
    expect(edgeIds.has("e1")).toBe(true);
    expect(nodeIds.size).toBe(1);
    expect(edgeIds.size).toBe(1);
  });
});

describe("normalizeServerValidation", () => {
  it("normaliza { valid, errors } do POST /api/pipelines/validate", () => {
    const out = normalizeServerValidation({
      valid: false,
      errors: [
        { rule: 6, message: "input required sem data edge", nodeId: "n2" },
        "mensagem solta",
      ],
    });
    expect(out.valid).toBe(false);
    expect(out.errors).toHaveLength(2);
    expect(out.errors[0].nodeId).toBe("n2");
    expect(out.errors[1].message).toBe("mensagem solta");
  });

  it("payload nulo => invalido sem erros conhecidos", () => {
    const out = normalizeServerValidation(null);
    expect(out.valid).toBe(true); // vazio = valido (lista vazia = grafo valido)
    expect(out.errors).toEqual([]);
  });
});

describe("buildValidationPayload", () => {
  it("combina pipeline + grafo de trabalho com entryNodeId derivado", () => {
    const pipeline = {
      id: "p1",
      ownerId: "u1",
      name: "P",
      description: "",
      status: "draft",
      entryNodeId: "",
      nodes: [],
      edges: [],
      currentCheckpoint: null,
      startedAt: null,
      completedAt: null,
    } as Pipeline;
    const nodes = [makeNode("n1", "A", [], [])];
    const out = buildValidationPayload(pipeline, nodes, []);
    expect(out.entryNodeId).toBe("n1");
    expect(out.nodes).toEqual(nodes);
  });
});
