"use client";

import { Server } from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";

/**
 * Placeholder: MCP servers (fe-library substitui).
 */
export default function McpPage() {
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
        MCP Servers
      </h1>
      <EmptyState
        icon={Server}
        title="Nenhum servidor MCP"
        description="Esta tela será implementada pelo nó fe-library."
      />
    </div>
  );
}
