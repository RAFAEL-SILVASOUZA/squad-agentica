import * as React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { StageStrip, buildStages } from "./stage-strip";
import { makePipeline } from "./test-fixtures";

describe("StageStrip", () => {
  it("orders agents topologically with approval gates and focuses a result on click", () => {
    const base = makePipeline();
    const pipeline = makePipeline({
      entryNodeId: "node-1",
      // node-2 vem antes no array, mas depende de node-1 (com aprovação).
      nodes: [base.nodes[1], base.nodes[0]],
      edges: [{ id: "e1", type: "flow", source: "node-1", target: "node-2", requiresApproval: true }],
    });
    const stages = buildStages(pipeline, { "node-1": "completed", "node-2": "waiting_approval" });
    expect(stages.map((s) => s.name)).toEqual(["Agent 1", "Aprovação", "Agent 2"]);

    const onSelect = vi.fn();
    render(<StageStrip steps={stages} onSelect={onSelect} />);
    expect(screen.getByRole("button", { name: /Agent 1.*Concluído/ })).toBeInTheDocument();
    expect(screen.getByText("Aprovação")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Agent 2/ }));
    expect(onSelect).toHaveBeenCalledWith("node-2");
  });

  it("keeps nodes unreachable from the entry at the end, and survives cycles", () => {
    const base = makePipeline();
    const pipeline = makePipeline({
      edges: [
        { id: "e1", type: "flow", source: "node-1", target: "node-1", requiresApproval: false },
      ],
      nodes: [base.nodes[1], base.nodes[0]],
    });
    expect(buildStages(pipeline, {}).map((s) => s.nodeId)).toEqual(["node-1", "node-2"]);
  });

  it("shows 'Mais etapas →' button when content overflows", () => {
    // Simula overflow: o container tem scrollWidth > clientWidth
    const base = makePipeline();
    const manyNodes = Array.from({ length: 15 }, (_, i) => ({
      id: `node-${i}`,
      agentId: `agent-${i}`,
      position: { x: i * 200, y: 100 },
      label: `Agent ${i}`,
      agentSnapshot: base.nodes[0].agentSnapshot,
    }));
    const manyEdges = Array.from({ length: 14 }, (_, i) => ({
      id: `edge-${i}`,
      type: "flow" as const,
      source: `node-${i}`,
      target: `node-${i + 1}`,
      requiresApproval: false,
    }));
    const pipeline = makePipeline({
      entryNodeId: "node-0",
      nodes: manyNodes,
      edges: manyEdges,
    });
    const stages = buildStages(pipeline, {});

    const { container } = render(<StageStrip steps={stages} onSelect={() => {}} />);
    const ol = container.querySelector("ol")!;

    // Simula overflow: scrollWidth > clientWidth
    Object.defineProperty(ol, "scrollWidth", { value: 2000, configurable: true });
    Object.defineProperty(ol, "clientWidth", { value: 800, configurable: true });
    Object.defineProperty(ol, "scrollLeft", { value: 0, configurable: true });

    // Dispara o evento de scroll dentro de act para o React processar o state
    act(() => {
      ol.dispatchEvent(new Event("scroll"));
    });

    // O botão "Mais etapas →" deve aparecer
    expect(screen.queryByRole("button", { name: /Mais etapas/ })).not.toBeNull();
  });
});
