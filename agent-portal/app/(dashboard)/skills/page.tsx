"use client";

import { BookOpen } from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";

/**
 * Placeholder: skills (fe-library substitui).
 */
export default function SkillsPage() {
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
        Skills
      </h1>
      <EmptyState
        icon={BookOpen}
        title="Nenhum skill ainda"
        description="Esta tela será implementada pelo nó fe-library."
      />
    </div>
  );
}
