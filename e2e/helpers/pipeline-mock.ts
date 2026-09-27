/**
 * Mock do CRUD de pipeline (workaround de F9/B1).
 *
 * O CRUD de pipeline (POST/GET/PUT /api/pipelines, POST /api/pipelines/validate)
 * não existe no backend (F9 = B1, dono rt-executor). As telas do editor
 * (/pipelines/{id}) e do monitor (/pipelines/{id}/run) chamam
 * GET/PUT /api/pipelines/{id} para carregar o grafo — sem isso, nenhuma tela
 * de pipeline funciona pela interface. Para exercitar a UI (arrastar, conectar,
 * validar, salvar, monitor), a suíte intercepta essas rotas com um estado
 * em memória alimentado pela pipeline semeada no banco (dbSeedPipeline).
 *
 * As rotas de runtime (execute, runs, checkpoints, pause/resume/stop) e as de
 * aprovação NÃO são mockadas: o backend real as serve, e o teste documenta o
 * comportamento real (F1, F7, F11 etc.).
 *
 * A decisão de mock é registrada no relatório (jornada -> F#/E#).
 */
import type { Page } from "@playwright/test";

export interface MockNode {
  id: string;
  agentId: string;
  position: { x: number; y: number };
  label?: string;
  agentSnapshot: Record<string, unknown>;
}

export interface MockEdge {
  id: string;
  type: "flow" | "data";
  source: string;
  target: string;
  condition?: { field: string; operator: string; value: string | string[] };
  label?: string;
  requiresApproval: boolean;
  approvalChannel?: string | null;
  approvalMessage?: string | null;
  dataMapping?: { sourceOutput: string; targetInput: string };
}

export interface MockPipelineState {
  id: string;
  name: string;
  description: string;
  status: string;
  entryNodeId: string;
  nodes: MockNode[];
  edges: MockEdge[];
  /** Payload gravado pelo último PUT (para inspeção no teste). */
  lastSave?: { nodes: MockNode[]; edges: MockEdge[] };
}

export interface PipelineMock {
  state: MockPipelineState;
  /** Desliga o mock (deixa o backend responder). */
  dispose(): Promise<void>;
}

export async function mockPipelineApi(
  page: Page,
  seed: {
    id: string;
    name?: string;
    entryNodeId: string;
    nodes: MockNode[];
    edges: MockEdge[];
    status?: string;
  }
): Promise<PipelineMock> {
  const state: MockPipelineState = {
    id: seed.id,
    name: seed.name ?? "Pipeline E2E",
    description: "semeada pela suite qa-e2e",
    status: seed.status ?? "draft",
    entryNodeId: seed.entryNodeId,
    nodes: seed.nodes,
    edges: seed.edges,
  };

  // GET /api/pipelines (listagem) e /api/pipelines/{id} (detalhe).
  await page.route(/\/api\/pipelines(?:\/|\?|$)/, async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/\/api\/pipelines$/, "");
    const reqPath = url.pathname + (url.search || "");

    // Lista: GET /api/pipelines
    if (route.request().method() === "GET" && url.pathname === "/api/pipelines") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [
            {
              id: state.id,
              name: state.name,
              description: state.description,
              status: state.status,
              nodes: state.nodes,
              edges: state.edges,
            },
          ],
          total: 1,
          page: 1,
          limit: 20,
        }),
      });
    }

    // Detalhe: GET /api/pipelines/{id}
    const detailMatch = url.pathname.match(/^\/api\/pipelines\/([0-9a-f-]{36})$/);
    if (route.request().method() === "GET" && detailMatch && detailMatch[1] === state.id) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(state),
      });
    }

    // Salvar: PUT /api/pipelines/{id}
    if (route.request().method() === "PUT" && detailMatch && detailMatch[1] === state.id) {
      const body = route.request().postDataJSON() as Partial<MockPipelineState>;
      if (Array.isArray(body.nodes)) state.nodes = body.nodes as MockNode[];
      if (Array.isArray(body.edges)) state.edges = body.edges as MockEdge[];
      if (typeof body.name === "string") state.name = body.name;
      if (typeof body.entryNodeId === "string" && body.entryNodeId) {
        state.entryNodeId = body.entryNodeId;
      }
      state.lastSave = { nodes: state.nodes, edges: state.edges };
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(state),
      });
    }

    // Validação: POST /api/pipelines/validate
    if (
      route.request().method() === "POST" &&
      url.pathname === "/api/pipelines/validate"
    ) {
      // O frontend valida localmente; o servidor devolve valid:true para não
      // duplicar os erros locais (mesmo contrato do endpoint real).
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ valid: true, errors: [] }),
      });
    }

    // Demais rotas de pipeline (execute, runs, ...): backend real.
    void reqPath;
    return route.continue();
  });

  return {
    state,
    dispose: async () => {
      await page.unroute(/\/api\/pipelines(?:\/|\?|$)/);
    },
  };
}

/**
 * Constrói o grafo de duas linhas (2 agentes) no formato que o FlowEditor e o
 * monitor esperam (PipelineNode/PipelineEdge camelCase, spec 4.2).
 */
export function twoNodeGraph(pipelineId: string, a1: { id: string; name: string }, a2: { id: string; name: string }) {
  const n1 = "node-" + a1.id.slice(0, 8);
  const n2 = "node-" + a2.id.slice(0, 8);
  const snapshot = (a: { id: string; name: string }) => ({
    agentId: a.id,
    version: 1,
    name: a.name,
    description: "qa-e2e",
    prompt: "Responda no campo result.",
    strategy: "react",
    skills: [],
    tools: [],
    mcpServers: [],
    knowledge: [],
    integrations: [],
    inputs: [{ name: "spec", type: "document", required: false }],
    outputs: [{ name: "result", type: "document", required: true }],
    actions: ["follow", "finalize"],
    model: "gpt-4o",
    maxIterations: 5,
    timeout: 60,
    shellAccess: false,
  });
  const nodes: MockNode[] = [
    { id: n1, agentId: a1.id, position: { x: 0, y: 0 }, label: a1.name, agentSnapshot: snapshot(a1) },
    { id: n2, agentId: a2.id, position: { x: 260, y: 0 }, label: a2.name, agentSnapshot: snapshot(a2) },
  ];
  const edges: MockEdge[] = [
    {
      id: "edge-flow-" + a1.id.slice(0, 8),
      type: "flow",
      source: n1,
      target: n2,
      requiresApproval: false,
    },
    {
      id: "edge-data-" + a1.id.slice(0, 8),
      type: "data",
      source: n1,
      target: n2,
      requiresApproval: false,
      dataMapping: { sourceOutput: "result", targetInput: "spec" },
    },
  ];
  void pipelineId;
  return { n1, n2, nodes, edges };
}
