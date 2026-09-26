"use client";

import { Bot } from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";

/**
 * Placeholder: detalhe/edição de agente (fe-agents substitui).
 */
export default function AgentDetailPage() {
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
        Agente
      </h1>
      <EmptyState
        icon={Bot}
        title="Detalhe do agente"
        description="Esta tela será implementada pelo nó fe-agents."
      />
    </div>
  );
}
