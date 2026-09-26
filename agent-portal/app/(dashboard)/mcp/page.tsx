"use client";

import { MCPServersLibrary } from "@/components/library/mcp-servers-library";

/**
 * MCP Servers (fe-library).
 * Registra, testa e lista servidores MCP com tools descobertas.
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
      <MCPServersLibrary />
    </div>
  );
}
