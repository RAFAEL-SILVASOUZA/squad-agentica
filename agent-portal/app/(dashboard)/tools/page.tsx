"use client";

import { Wrench } from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";

/**
 * Placeholder: tools custom (fe-library substitui).
 */
export default function ToolsPage() {
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
        Tools Custom
      </h1>
      <EmptyState
        icon={Wrench}
        title="Nenhuma tool ainda"
        description="Esta tela será implementada pelo nó fe-library."
      />
    </div>
  );
}
