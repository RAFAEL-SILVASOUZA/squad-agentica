"use client";

import * as React from "react";
import Link from "next/link";
import { Bot, ArrowRight } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { BadgeStatus } from "@/components/ui/badge";
import type { Agent } from "@/lib/types";

/**
 * Card de agente (design system §2.7, protótipo view-dashboard).
 * Nome, tipo, status e tags (integrations). Clicável → /agents/{id}.
 * Sem emojis; ícone via lucide-react.
 */

export interface AgentCardProps {
  agent: Agent;
  /**
   * Status operacional do agente (derivado do dashboard: se aparece em
   * pipeline em execução → "running"; senão "idle"). O tipo Agent da API
   * não carrega status operacional (decisão registrada no handoff).
   */
  status?: "running" | "idle";
}

const STATUS_LABEL: Record<"running" | "idle", string> = {
  running: "Executando",
  idle: "Ocioso",
};

const STATUS_BADGE: Record<"running" | "idle", BadgeStatus> = {
  running: "running",
  idle: "neutral",
};

function agentTags(agent: Agent): string[] {
  const tags: string[] = [];
  for (const integration of agent.integrations ?? []) {
    tags.push(integration.platform);
  }
  for (const skill of agent.skills ?? []) {
    tags.push(skill.skillId);
  }
  return tags.slice(0, 3);
}

export function AgentCard({ agent, status = "idle" }: AgentCardProps) {
  const tags = agentTags(agent);

  return (
    <Link
      href={`/agents/${agent.id}`}
      aria-label={`Abrir agente ${agent.name}`}
      style={{ display: "block", textDecoration: "none", color: "inherit" }}
    >
      <Card hoverable style={{ height: "100%" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "10px",
            marginBottom: "10px",
          }}
        >
          <span
            aria-hidden="true"
            style={{
              width: 32,
              height: 32,
              borderRadius: "var(--radius-sm)",
              background: "var(--accent-subtle)",
              color: "var(--accent)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            <Bot size={16} aria-hidden="true" />
          </span>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div
              style={{
                fontSize: "13px",
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
                fontSize: "11px",
                color: "var(--text-secondary)",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {agent.type}
            </div>
          </div>
          <ArrowRight
            size={14}
            aria-hidden="true"
            style={{ color: "var(--text-muted)", flexShrink: 0 }}
          />
        </div>

        <Badge status={STATUS_BADGE[status]} label={STATUS_LABEL[status]} />

        {tags.length > 0 && (
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "4px",
              marginTop: "10px",
            }}
          >
            {tags.map((tag) => (
              <span
                key={tag}
                style={{
                  fontSize: "10px",
                  color: "var(--text-secondary)",
                  background: "var(--bg-hover)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "10px",
                  padding: "1px 8px",
                }}
              >
                {tag}
              </span>
            ))}
          </div>
        )}
      </Card>
    </Link>
  );
}
