"use client";

import * as React from "react";
import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";
import { Bot, Zap } from "lucide-react";
import type { AgentSnapshot, PortDef } from "@/lib/types";

/**
 * Data shape for a pipeline node in React Flow.
 */
export interface AgentNodeData {
  label?: string;
  agentSnapshot: AgentSnapshot;
  inputs: PortDef[];
  outputs: PortDef[];
  isEntry?: boolean;
  [key: string]: unknown;
}

export type AgentNode = Node<AgentNodeData>;

/**
 * Custom node rendering an agent with input/output ports.
 * Design: DESIGN-SYSTEM.md §2.19
 */
export function AgentNode({ data, selected }: NodeProps<AgentNode>) {
  const { label, agentSnapshot, inputs, outputs, isEntry, hasError } = data;

  const borderColor = hasError
    ? "var(--error)"
    : selected
      ? "var(--accent)"
      : "var(--border)";

  return (
    <div
      className="flow-node"
      style={{
        width: 160,
        background: "var(--bg-elevated)",
        border: `1px solid ${borderColor}`,
        borderRadius: "var(--radius)",
        padding: 14,
        cursor: "grab",
        transition: "border-color 0.2s",
        position: "relative",
        outline: hasError ? "2px solid var(--error)" : "none",
        outlineOffset: 2,
      }}
    >
      {/* Entry indicator */}
      {isEntry && (
        <div
          style={{
            position: "absolute",
            top: -8,
            left: 12,
            background: "var(--accent)",
            color: "#fff",
            fontSize: 9,
            fontWeight: 600,
            padding: "1px 6px",
            borderRadius: 4,
            textTransform: "uppercase",
            letterSpacing: "0.5px",
          }}
        >
          Entry
        </div>
      )}

      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginBottom: 8,
        }}
      >
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: 6,
            background: "var(--accent-subtle)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--accent)",
            flexShrink: 0,
          }}
        >
          <Bot size={16} aria-hidden="true" />
        </div>
        <div style={{ overflow: "hidden" }}>
          <div
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: "var(--text)",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {label || agentSnapshot.name}
          </div>
          <div
            style={{
              fontSize: 10,
              color: "var(--text-muted)",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {agentSnapshot.description ? agentSnapshot.description.slice(0, 20) : "Agent"}
          </div>
        </div>
      </div>

      {/* Ports */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginTop: 10,
          gap: 4,
        }}
      >
        {/* Input ports (left side) */}
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {inputs.map((port) => (
            <div key={port.name} style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <Handle
                id={port.name}
                type="target"
                position={Position.Left}
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: "50%",
                  border: "2px solid var(--info)",
                  background: "var(--bg-elevated)",
                }}
              />
              <span
                style={{
                  fontSize: 9,
                  color: "var(--text-muted)",
                  maxWidth: 50,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={port.name}
              >
                {port.name}
              </span>
            </div>
          ))}
        </div>

        {/* Output ports (right side) */}
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {outputs.map((port) => (
            <div key={port.name} style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <span
                style={{
                  fontSize: 9,
                  color: "var(--text-muted)",
                  maxWidth: 50,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={port.name}
              >
                {port.name}
              </span>
              <Handle
                id={port.name}
                type="source"
                position={Position.Right}
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: "50%",
                  border: "2px solid var(--success)",
                  background: "var(--bg-elevated)",
                }}
              />
            </div>
          ))}
        </div>
      </div>

      {/* Actions indicator */}
      {agentSnapshot.actions && agentSnapshot.actions.length > 0 && (
        <div
          style={{
            marginTop: 8,
            display: "flex",
            alignItems: "center",
            gap: 4,
            fontSize: 9,
            color: "var(--text-muted)",
          }}
        >
          <Zap size={10} aria-hidden="true" />
          <span>{agentSnapshot.actions.join(" · ")}</span>
        </div>
      )}
    </div>
  );
}
