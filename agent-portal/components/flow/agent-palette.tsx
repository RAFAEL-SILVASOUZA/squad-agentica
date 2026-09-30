"use client";

import * as React from "react";
import { Bot, Plus, X, Search } from "lucide-react";
import type { Agent } from "@/lib/types";

interface AgentPaletteProps {
  agents: Agent[];
  onAddAgent: (agent: Agent) => void;
  onClose: () => void;
}

/**
 * Palette showing available agents to drag/click onto the canvas.
 * Design: DESIGN-SYSTEM.md §2.19 (node styling)
 */
export function AgentPalette({ agents, onAddAgent, onClose }: AgentPaletteProps) {
  const [search, setSearch] = React.useState("");
  const filtered = agents.filter((a) =>
    a.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div
      role="dialog"
      aria-label="Adicionar agente ao pipeline"
      style={{
        position: "absolute",
        top: 56,
        left: 12,
        width: 260,
        maxHeight: "calc(100% - 80px)",
        background: "var(--bg-elevated)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius)",
        boxShadow: "var(--shadow-lg)",
        zIndex: 10,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "10px 14px",
          borderBottom: "1px solid var(--border-subtle)",
        }}
      >
        <span
          style={{
            fontSize: 12,
            fontWeight: 600,
            color: "var(--text)",
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          <Plus size={14} aria-hidden="true" />
          Adicionar agente
        </span>
        <button
          onClick={onClose}
          aria-label="Fechar paleta"
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            color: "var(--text-muted)",
            padding: 4,
            borderRadius: 4,
            display: "flex",
            alignItems: "center",
          }}
        >
          <X size={14} aria-hidden="true" />
        </button>
      </div>

      {/* Busca */}
      <div style={{ padding: "8px 8px 0" }}>
        <div style={{ position: "relative" }}>
          <Search
            size={13}
            aria-hidden="true"
            style={{ position: "absolute", left: 8, top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }}
          />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar agente…"
            aria-label="Buscar agente por nome"
            style={{
              width: "100%",
              padding: "6px 8px 6px 28px",
              borderRadius: "var(--radius-sm)",
              border: "1px solid var(--border)",
              background: "var(--bg-elevated)",
              color: "var(--text)",
              fontSize: 12,
              outline: "none",
              boxSizing: "border-box",
            }}
          />
        </div>
      </div>

      {/* Agent list */}
      <div style={{ overflowY: "auto", padding: 8 }}>
        {agents.length === 0 ? (
          <div
            style={{
              padding: "20px 14px",
              textAlign: "center",
              fontSize: 12,
              color: "var(--text-muted)",
            }}
          >
            Nenhum agente disponível.
            <br />
            <span style={{ fontSize: 11 }}>Crie um agente primeiro.</span>
          </div>
        ) : (
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 4 }}>
            {filtered.map((agent) => (
              <li key={agent.id}>
                <button
                  onClick={() => onAddAgent(agent)}
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData("application/agent-id", agent.id);
                    e.dataTransfer.effectAllowed = "move";
                  }}
                  style={{
                    width: "100%",
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: "8px 10px",
                    background: "var(--bg-hover)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-sm)",
                    cursor: "grab",
                    transition: "border-color 0.2s",
                    textAlign: "left",
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
                    <Bot size={14} aria-hidden="true" />
                  </div>
                  <div style={{ overflow: "hidden", flex: 1 }}>
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
                      {agent.name}
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
                      {agent.type || "Agent"}
                    </div>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
