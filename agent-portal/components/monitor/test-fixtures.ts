/** Fixtures compartilhadas pelos testes do monitor. */
import type { Pipeline, PipelineRun, Checkpoint, AgentSnapshot } from "@/lib/types";

function snapshot(agentId: string, name: string, overrides: Partial<AgentSnapshot> = {}): AgentSnapshot {
  return {
    agentId,
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
    inputs: [],
    outputs: [],
    actions: ["follow"],
    model: "gpt-4o",
    maxIterations: 5,
    timeout: 300,
    shellAccess: false,
    ...overrides,
  };
}

export function makePipeline(overrides: Partial<Pipeline> = {}): Pipeline {
  return {
    id: "pipe-1",
    ownerId: "owner-1",
    name: "Test Pipeline",
    description: "A test pipeline",
    status: "draft",
    entryNodeId: "node-1",
    nodes: [
      {
        id: "node-1",
        agentId: "agent-1",
        position: { x: 100, y: 100 },
        label: "Agent 1",
        agentSnapshot: snapshot("agent-1", "Agent 1", {
          inputs: [{ name: "task", type: "string", required: true }],
          outputs: [{ name: "result", type: "string", required: true }],
        }),
      },
      {
        id: "node-2",
        agentId: "agent-2",
        position: { x: 300, y: 100 },
        label: "Agent 2",
        agentSnapshot: snapshot("agent-2", "Agent 2", {
          inputs: [{ name: "input", type: "string", required: true }],
          outputs: [{ name: "output", type: "string", required: true }],
          actions: ["finalize"],
          maxIterations: 3,
          timeout: 120,
        }),
      },
    ],
    edges: [
      {
        id: "edge-1",
        type: "flow",
        source: "node-1",
        target: "node-2",
        requiresApproval: false,
      },
    ],
    currentCheckpoint: null,
    startedAt: null,
    completedAt: null,
    repository: null,
    ...overrides,
  };
}

export function makeRun(overrides: Partial<PipelineRun> = {}): PipelineRun {
  return {
    id: "run-1",
    pipelineId: "pipe-1",
    threadId: "thread-1",
    status: "running",
    startedAt: new Date().toISOString(),
    ...overrides,
  };
}

export function makeCheckpoint(overrides: Partial<Checkpoint> = {}): Checkpoint {
  return {
    id: "cp-1",
    pipelineId: "pipe-1",
    nodeId: "node-1",
    state: {},
    timestamp: new Date().toISOString(),
    status: "completed",
    metadata: {},
    ...overrides,
  };
}
