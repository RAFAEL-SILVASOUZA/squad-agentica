"use client";

import * as React from "react";
import {
  BaseEdge,
  EdgeLabelRenderer,
  getSmoothStepPath,
  type EdgeProps,
  type Edge,
} from "@xyflow/react";
import { Shield } from "lucide-react";

/**
 * Data shape for a pipeline edge in React Flow.
 */
export interface PipelineEdgeData {
  edgeType: "flow" | "data";
  condition?: { field: string; operator: string; value: string | string[] };
  label?: string;
  requiresApproval?: boolean;
  dataMapping?: { sourceOutput: string; targetInput: string };
  [key: string]: unknown;
}

/**
 * Custom edge rendering with distinct visuals for flow vs data edges.
 * Design: DESIGN-SYSTEM.md §2.19
 *
 * Flow (default): solid, var(--text-muted), opacity 0.5, width 1.5
 * Flow (active): solid, var(--accent), opacity 1, width 2
 * Data: dashed 5,4, var(--info), opacity 0.85, width 1.5
 * Flow condition: dashed 5,5, var(--text-muted), opacity 0.5, width 1.5
 */
export function PipelineEdgeComponent({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
}: EdgeProps) {
  const [edgePath] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    borderRadius: 8,
  });

  const edgeData = data as unknown as PipelineEdgeData | undefined;
  const isData = edgeData?.edgeType === "data";
  const hasCondition = !!edgeData?.condition;
  const requiresApproval = !!edgeData?.requiresApproval;

  // Determine stroke style
  let stroke: string;
  let strokeDasharray: string | undefined;
  let strokeWidth: number;
  let opacity: number;

  if (isData) {
    stroke = "var(--info)";
    strokeDasharray = "5,4";
    strokeWidth = 1.5;
    opacity = 0.85;
  } else if (hasCondition) {
    stroke = "var(--text-muted)";
    strokeDasharray = "5,5";
    strokeWidth = 1.5;
    opacity = 0.5;
  } else {
    stroke = selected ? "var(--accent)" : "var(--text-muted)";
    strokeDasharray = undefined;
    strokeWidth = selected ? 2 : 1.5;
    opacity = selected ? 1 : 0.5;
  }

  // Build label
  let label: string | undefined;
  if (edgeData?.label) {
    label = edgeData.label;
  } else if (isData && edgeData?.dataMapping) {
    label = `${edgeData.dataMapping.sourceOutput} → ${edgeData.dataMapping.targetInput}`;
  } else if (hasCondition && edgeData?.condition) {
    const cond = edgeData.condition;
    label = `${cond.field} ${cond.operator} ${Array.isArray(cond.value) ? cond.value.join(",") : cond.value}`;
  }

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke,
          strokeWidth,
          strokeDasharray,
          opacity,
        }}
        markerEnd="url(#arrowhead)"
      />
      {label && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${(sourceX + targetX) / 2}px, ${(sourceY + targetY) / 2}px)`,
              fontSize: 10,
              color: "var(--text-muted)",
              background: "var(--bg-elevated)",
              padding: "1px 6px",
              borderRadius: 4,
              border: "1px solid var(--border)",
              whiteSpace: "nowrap",
              pointerEvents: "none",
            }}
          >
            {requiresApproval && (
              <Shield size={9} style={{ marginRight: 3, verticalAlign: "middle" }} aria-hidden="true" />
            )}
            {label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
