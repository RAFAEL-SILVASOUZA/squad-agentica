"use client";

import { GitBranch } from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";

/**
 * Placeholder: editor de pipeline (fe-flow-editor substitui).
 */
export default function PipelineEditorPage() {
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
        Editor de Pipeline
      </h1>
      <EmptyState
        icon={GitBranch}
        title="Editor de fluxo"
        description="Esta tela será implementada pelo nó fe-flow-editor."
      />
    </div>
  );
}
