import * as React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AgentNode } from "./agent-node";
import type { AgentNodeData } from "./agent-node";
import type { AgentSnapshot } from "@/lib/types";

const mockSnapshot: AgentSnapshot = {
  agentId: "agent-1",
  version: 1,
  name: "Backend Developer",
  description: "Develops backend code",
  prompt: "You are a backend developer",
  strategy: "Step by step",
  skills: [],
  tools: [],
  mcpServers: [],
  knowledge: [],
  integrations: [],
  inputs: [
    { name: "task", type: "string", required: true },
    { name: "context", type: "object", required: false },
  ],
  outputs: [
    { name: "code", type: "string", required: true },
    { name: "errors", type: "array", required: false },
  ],
  actions: ["follow", "return"],
  model: "gpt-4o",
  maxIterations: 5,
  timeout: 300,
  shellAccess: false,
};

const mockData: AgentNodeData = {
  label: "Backend Developer",
  agentSnapshot: mockSnapshot,
  inputs: mockSnapshot.inputs,
  outputs: mockSnapshot.outputs,
  isEntry: false,
};

// Mock React Flow Handle component (not available outside ReactFlowProvider)
vi.mock("@xyflow/react", () => ({
  Handle: ({ id, type, position, style }: { id: string; type: string; position: string; style?: React.CSSProperties }) => (
    <div data-testid={`handle-${type}-${id}`} data-position={position} style={style} />
  ),
  Position: { Left: "Left", Right: "Right", Top: "Top", Bottom: "Bottom" },
}));

describe("AgentNode", () => {
  // eslint-disable-next-line
  const renderNode = (data: AgentNodeData, selected = false) => {
    // eslint-disable-next-line
    const props = { id: "test-node", data, selected } as any;
    return render(<AgentNode {...props} />);
  };

  it("renders agent name", () => {
    renderNode(mockData);
    expect(screen.getByText("Backend Developer")).toBeInTheDocument();
  });

  it("renders input ports", () => {
    renderNode(mockData);
    expect(screen.getByTestId("handle-target-task")).toBeInTheDocument();
    expect(screen.getByTestId("handle-target-context")).toBeInTheDocument();
  });

  it("renders output ports", () => {
    renderNode(mockData);
    expect(screen.getByTestId("handle-source-code")).toBeInTheDocument();
    expect(screen.getByTestId("handle-source-errors")).toBeInTheDocument();
  });

  it("shows entry badge when isEntry is true", () => {
    const entryData: AgentNodeData = { ...mockData, isEntry: true };
    renderNode(entryData);
    expect(screen.getByText("Entry")).toBeInTheDocument();
  });

  it("does not show entry badge when isEntry is false", () => {
    renderNode(mockData);
    expect(screen.queryByText("Entry")).not.toBeInTheDocument();
  });

  it("shows actions when present", () => {
    renderNode(mockData);
    expect(screen.getByText("follow · return")).toBeInTheDocument();
  });

  it("does not show actions when empty", () => {
    const noActionsData: AgentNodeData = {
      ...mockData,
      agentSnapshot: { ...mockSnapshot, actions: [] },
    };
    renderNode(noActionsData);
    expect(screen.queryByText("follow · return")).not.toBeInTheDocument();
  });

  it("uses accent border when selected", () => {
    const { container } = renderNode(mockData, true);
    const node = container.querySelector(".flow-node");
    expect(node).toHaveAttribute("style", expect.stringContaining("var(--accent)"));
  });

  it("uses default border when not selected", () => {
    const { container } = renderNode(mockData, false);
    const node = container.querySelector(".flow-node");
    expect(node).toHaveAttribute("style", expect.stringContaining("var(--border)"));
  });
});
