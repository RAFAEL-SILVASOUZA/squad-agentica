"use client";

import { Bot } from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";

/**
 * Placeholder: criar novo agente (fe-agents substitui).
 */
export default function NewAgentPage() {
  return (
    <div>
      <h1
        style={{
          fontSize: "20px",
          fontWeight: 700,
          color: "var(--text)",
          margin: "0 0 24px",
        }}
      >
        Novo Agente
      </h1>
      <EmptyState
        icon={Bot}
        title="Construção de agente"
        description="Esta tela será implementada pelo nó fe-agents."
      />
    </div>
  );
}
