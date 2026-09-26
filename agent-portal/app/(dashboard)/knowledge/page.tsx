"use client";

import { FileText } from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";

/**
 * Placeholder: knowledge base (fe-library substitui).
 */
export default function KnowledgePage() {
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
        Knowledge
      </h1>
      <EmptyState
        icon={FileText}
        title="Nenhuma base de conhecimento"
        description="Esta tela será implementada pelo nó fe-library."
      />
    </div>
  );
}
