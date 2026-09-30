"use client";

import * as React from "react";
import { CheckCircle2, Circle } from "lucide-react";
import { Card } from "@/components/ui/card";

/**
 * Checklist de onboarding "Primeiros passos" do dashboard.
 * Aparece enquanto o portal não tiver os 4 itens básicos.
 * Um item é marcado quando a condição correspondente é verdadeira.
 * Sem emojis; ícones via lucide-react.
 */

export interface OnboardingChecklistProps {
  hasAgent: boolean;
  hasPipeline: boolean;
  hasKnowledge: boolean;
  hasMcp: boolean;
}

interface ChecklistItem {
  label: string;
  done: boolean;
}

export function OnboardingChecklist({
  hasAgent,
  hasPipeline,
  hasKnowledge,
  hasMcp,
}: OnboardingChecklistProps) {
  const items: ChecklistItem[] = [
    { label: "Crie um agente", done: hasAgent },
    { label: "Crie uma pipeline", done: hasPipeline },
    { label: "Adicione uma base de conhecimento", done: hasKnowledge },
    { label: "Conecte uma ferramenta (MCP)", done: hasMcp },
  ];

  return (
    <Card style={{ marginBottom: "24px" }}>
      <h2
        style={{
          fontSize: "13px",
          fontWeight: 600,
          color: "var(--text-secondary)",
          textTransform: "uppercase",
          letterSpacing: "0.5px",
          margin: "0 0 10px",
        }}
      >
        Primeiros passos
      </h2>
      <ul
        style={{
          listStyle: "none",
          margin: 0,
          padding: 0,
          display: "flex",
          flexDirection: "column",
          gap: "8px",
        }}
      >
        {items.map((item) => (
          <li
            key={item.label}
            data-done={item.done}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              fontSize: "13px",
              color: item.done ? "var(--text-secondary)" : "var(--text)",
            }}
          >
            {item.done ? (
              <CheckCircle2
                size={15}
                aria-hidden="true"
                style={{ color: "var(--success)", flexShrink: 0 }}
              />
            ) : (
              <Circle
                size={15}
                aria-hidden="true"
                style={{ color: "var(--text-muted)", flexShrink: 0 }}
              />
            )}
            {item.label}
          </li>
        ))}
      </ul>
    </Card>
  );
}
