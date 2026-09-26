"use client";

import { KnowledgeView } from "@/components/library/knowledge-view";
import { GitHubIntegration } from "@/components/library/github-integration";

/**
 * Knowledge (fe-library).
 * Sidebar de bases, criar base com escopo, upload de documentos,
 * consulta de teste com resultados e score. Rivvn desabilitado.
 * Integração GitHub com token de segredo.
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
      <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
        <KnowledgeView />
        <GitHubIntegration />
      </div>
    </div>
  );
}
