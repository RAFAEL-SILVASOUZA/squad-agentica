"use client";

import { Monitor } from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";

/**
 * Placeholder: monitor de pipeline (fe-monitor substitui).
 */
export default function PipelineRunPage() {
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
        Monitor
      </h1>
      <EmptyState
        icon={Monitor}
        title="Monitor de execução"
        description="Esta tela será implementada pelo nó fe-monitor."
      />
    </div>
  );
}
