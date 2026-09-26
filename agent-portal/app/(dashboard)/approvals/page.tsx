"use client";

import { CheckCircle2 } from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";

/**
 * Placeholder: aprovações (fe-approvals substitui).
 */
export default function ApprovalsPage() {
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
        Aprovações
      </h1>
      <EmptyState
        icon={CheckCircle2}
        title="Nenhuma aprovação pendente"
        description="Esta tela será implementada pelo nó fe-approvals."
      />
    </div>
  );
}
