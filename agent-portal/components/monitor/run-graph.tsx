"use client";

import * as React from "react";
import {
  ReactFlow,
  Background,
  MiniMap,
  useNodesState,
  useEdgesState,
  useReactFlow,
  type Node,
  type Edge,
  type NodeTypes,
  type EdgeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Maximize, ZoomIn, ZoomOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AgentNode, type AgentNodeData } from "@/components/flow/agent-node";
import { PipelineEdgeComponent, type PipelineEdgeData } from "@/components/flow/pipeline-edge";
import type { Pipeline } from "@/lib/types";
import { NODE_STATUS_LABEL, type NodeStatus } from "./status";

const nodeTypes: NodeTypes = {
  agent: AgentNode as unknown as NodeTypes["agent"],
};

const edgeTypes: EdgeTypes = {
  pipeline: PipelineEdgeComponent as unknown as EdgeTypes["pipeline"],
};

const STATUS_RING: Record<NodeStatus, string | null> = {
  pending: null,
  running: "var(--info)",
  completed: "var(--success)",
  failed: "var(--error)",
  waiting_approval: "var(--warning)",
};

function toFlowNodes(pipeline: Pipeline, statuses: Record<string, NodeStatus>): Node<AgentNodeData>[] {
  return pipeline.nodes.map((pn) => {
    const ring = STATUS_RING[statuses[pn.id] ?? "pending"];
    return {
      id: pn.id,
      type: "agent",
      position: pn.position,
      style: ring ? { boxShadow: `0 0 0 2px ${ring}`, borderRadius: "var(--radius)" } : undefined,
      data: {
        label: pn.label ?? pn.agentSnapshot.name,
        agentSnapshot: pn.agentSnapshot,
        inputs: pn.agentSnapshot.inputs ?? [],
        outputs: pn.agentSnapshot.outputs ?? [],
        isEntry: pn.id === pipeline.entryNodeId,
      },
    };
  });
}

function toFlowEdges(pipeline: Pipeline): Edge<PipelineEdgeData>[] {
  return pipeline.edges.map((pe) => ({
    id: pe.id,
    source: pe.source,
    target: pe.target,
    type: "pipeline",
    data: {
      edgeType: pe.type,
      condition: pe.condition,
      label: pe.label,
      requiresApproval: pe.requiresApproval,
      dataMapping: pe.dataMapping,
    },
  }));
}

export interface RunGraphProps {
  pipeline: Pipeline;
  statuses: Record<string, NodeStatus>;
  onNodeSelect: (nodeId: string) => void;
}

const LEGEND: NodeStatus[] = ["running", "completed", "failed", "waiting_approval"];

/**
 * Grafo da pipeline em modo leitura, com o status de cada nó (anel colorido).
 * Fica no modal "Ver grafo" do monitor; precisa de um ReactFlowProvider acima.
 */
export function RunGraph({ pipeline, statuses, onNodeSelect }: RunGraphProps) {
  const { zoomIn, zoomOut, fitView } = useReactFlow();
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<AgentNodeData>>(toFlowNodes(pipeline, statuses));
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge<PipelineEdgeData>>(toFlowEdges(pipeline));

  React.useEffect(() => {
    setNodes(toFlowNodes(pipeline, statuses));
    setEdges(toFlowEdges(pipeline));
  }, [pipeline, statuses, setNodes, setEdges]);

  return (
    <div
      style={{
        position: "relative",
        height: "70vh",
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius)",
        overflow: "hidden",
      }}
    >
      <div style={{ position: "absolute", top: 12, left: 12, display: "flex", gap: 4, zIndex: 5 }}>
        <Button size="sm" onClick={() => zoomOut({ duration: 200 })} aria-label="Zoom out">
          <ZoomOut size={13} aria-hidden="true" />
        </Button>
        <Button size="sm" onClick={() => zoomIn({ duration: 200 })} aria-label="Zoom in">
          <ZoomIn size={13} aria-hidden="true" />
        </Button>
        <Button size="sm" onClick={() => fitView({ padding: 0.2, duration: 300 })} aria-label="Fit to view">
          <Maximize size={13} aria-hidden="true" />
        </Button>
      </div>

      <div
        style={{
          position: "absolute",
          bottom: 12,
          left: 12,
          zIndex: 5,
          display: "flex",
          gap: 12,
          padding: "6px 10px",
          fontSize: 11,
          color: "var(--text-muted)",
          background: "var(--bg-elevated)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-sm)",
          boxShadow: "var(--shadow)",
        }}
      >
        {LEGEND.map((status) => (
          <span key={status} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: STATUS_RING[status] ?? undefined,
                display: "inline-block",
              }}
            />
            {NODE_STATUS_LABEL[status]}
          </span>
        ))}
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={(_, node) => onNodeSelect(node.id)}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        minZoom={0.1}
        maxZoom={2.0}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={true}
        deleteKeyCode={null}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={24} size={1} color="var(--border)" />
        <MiniMap
          nodeColor="var(--bg-hover)"
          maskColor="var(--bg)"
          style={{
            background: "var(--bg-elevated)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)",
          }}
        />
        <defs>
          <marker
            id="arrowhead"
            viewBox="0 0 10 10"
            refX={10}
            refY={5}
            markerWidth={8}
            markerHeight={8}
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--text-muted)" />
          </marker>
        </defs>
      </ReactFlow>
    </div>
  );
}
