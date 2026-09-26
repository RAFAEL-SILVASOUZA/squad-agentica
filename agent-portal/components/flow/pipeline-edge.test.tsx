import * as React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { PipelineEdgeComponent } from "./pipeline-edge";
import type { PipelineEdgeData } from "./pipeline-edge";

// Mock @xyflow/react
vi.mock("@xyflow/react", () => ({
  BaseEdge: ({ id, path, style, markerEnd }: { id: string; path: string; style?: React.CSSProperties; markerEnd?: string }) => (
    <svg data-testid="base-edge" data-id={id} data-path={path} data-marker={markerEnd}>
      <path d={path} style={style} />
    </svg>
  ),
  EdgeLabelRenderer: ({ children }: { children: React.ReactNode }) => <div data-testid="edge-label">{children}</div>,
  getSmoothStepPath: (opts: { sourceX: number; sourceY: number; targetX: number; targetY: number }) => [
    `M ${opts.sourceX},${opts.sourceY} L ${opts.targetX},${opts.targetY}`,
    { x: (opts.sourceX + opts.targetX) / 2, y: (opts.sourceY + opts.targetY) / 2 },
  ],
}));

const baseProps = {
  id: "edge-1",
  sourceX: 0,
  sourceY: 0,
  targetX: 200,
  targetY: 100,
  sourcePosition: "right" as const,
  targetPosition: "left" as const,
  selected: false,
  source: "node-1",
  target: "node-2",
  type: "pipeline" as const,
};

describe("PipelineEdgeComponent", () => {
  // eslint-disable-next-line
  const renderEdge = (data: PipelineEdgeData, selected = false) => {
    // eslint-disable-next-line
    const props = { ...baseProps, data, selected } as any;
    return render(<PipelineEdgeComponent {...props} />);
  };

  it("renders a flow edge with solid stroke", () => {
    const data: PipelineEdgeData = { edgeType: "flow", requiresApproval: false };
    const { container } = renderEdge(data);
    const path = container.querySelector("path");
    expect(path).toBeInTheDocument();
    // Flow edge: no dasharray
    expect(path?.getAttribute("style") || "").not.toContain("stroke-dasharray");
  });

  it("renders a data edge with dashed stroke", () => {
    const data: PipelineEdgeData = {
      edgeType: "data",
      requiresApproval: false,
      dataMapping: { sourceOutput: "code", targetInput: "task" },
    };
    const { container } = renderEdge(data);
    const path = container.querySelector("path");
    const style = path?.getAttribute("style") || "";
    expect(style).toContain("5,4");
  });

  it("renders a conditional flow edge with dashed stroke", () => {
    const data: PipelineEdgeData = {
      edgeType: "flow",
      condition: { field: "action", operator: "eq", value: "follow" },
      requiresApproval: false,
    };
    const { container } = renderEdge(data);
    const path = container.querySelector("path");
    const style = path?.getAttribute("style") || "";
    expect(style).toContain("5,5");
  });

  it("shows data mapping label for data edges", () => {
    const data: PipelineEdgeData = {
      edgeType: "data",
      requiresApproval: false,
      dataMapping: { sourceOutput: "code", targetInput: "task" },
    };
    renderEdge(data);
    expect(screen.getByText("code → task")).toBeInTheDocument();
  });

  it("shows condition label for conditional flow edges", () => {
    const data: PipelineEdgeData = {
      edgeType: "flow",
      condition: { field: "action", operator: "eq", value: "follow" },
      requiresApproval: false,
    };
    renderEdge(data);
    expect(screen.getByText("action eq follow")).toBeInTheDocument();
  });

  it("shows custom label when provided", () => {
    const data: PipelineEdgeData = {
      edgeType: "flow",
      label: "approved",
      requiresApproval: false,
    };
    renderEdge(data);
    expect(screen.getByText("approved")).toBeInTheDocument();
  });

  it("shows approval shield icon when requiresApproval is true", () => {
    const data: PipelineEdgeData = {
      edgeType: "flow",
      label: "needs approval",
      requiresApproval: true,
    };
    const { container } = renderEdge(data);
    // Shield icon is rendered as an SVG
    const label = container.querySelector("[data-testid='edge-label']");
    expect(label).toBeInTheDocument();
    expect(label?.querySelector("svg")).toBeInTheDocument();
  });

  it("uses accent color for selected flow edge", () => {
    const data: PipelineEdgeData = { edgeType: "flow", requiresApproval: false };
    const { container } = renderEdge(data, true);
    const path = container.querySelector("path");
    const style = path?.getAttribute("style") || "";
    expect(style).toContain("var(--accent)");
  });

  it("does not render label when no label/condition/dataMapping", () => {
    const data: PipelineEdgeData = { edgeType: "flow", requiresApproval: false };
    renderEdge(data);
    expect(screen.queryByTestId("edge-label")).not.toBeInTheDocument();
  });
});
