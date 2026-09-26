"use client";

import { SkillsLibrary } from "@/components/library/skills-library";

/**
 * Skills (fe-library).
 * Lista, cria, edita e exclui skills com editor markdown + preview.
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
      <SkillsLibrary />
    </div>
  );
}
