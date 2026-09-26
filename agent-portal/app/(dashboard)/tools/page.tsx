"use client";

import { ToolsEditor } from "@/components/library/tools-editor";

/**
 * Tools Custom (fe-library).
 * Lista, cria, edita, valida, deploya e testa tools custom.
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
      <ToolsEditor />
    </div>
  );
}
