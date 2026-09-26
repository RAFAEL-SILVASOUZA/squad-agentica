"use client";

import { KnowledgeView } from "@/components/library/knowledge-view";

/**
 * Knowledge (fe-library).
 * Sidebar de bases, criar base com escopo, upload de documentos,
 * consulta de teste com resultados e score. Rivvn desabilitado.
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
      <KnowledgeView />
    </div>
  );
}
