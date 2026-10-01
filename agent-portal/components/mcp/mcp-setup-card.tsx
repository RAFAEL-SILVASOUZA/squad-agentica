"use client";

import React from "react";
import { Button } from "@/components/ui";
import { Card } from "@/components/ui";
import { Copy } from "lucide-react";
import { useToast } from "@/components/ui";

export function MCPSetupCard() {
  const { addToast } = useToast();
  const mcpUrl = "http://localhost/mcp/mcp";

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(mcpUrl);
      addToast("success", "URL do servidor copiada para a área de transferência.");
    } catch (err) {
      addToast("error", "Não foi possível copiar a URL.");
    }
  };

  const configExample = {
    mcpServers: {
      "agent-portal": {
        url: mcpUrl,
      },
    },
  };

  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
        <div>
          <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 600 }}>URL do Servidor MCP</h3>
          <p style={{ margin: "4px 0 0", fontSize: "14px", color: "var(--text-secondary)" }}>
            Use este endereço para conectar seu cliente MCP ao Agent Portal.
          </p>
        </div>
        <Button onClick={copyToClipboard} variant="default" size="sm" style={{ display: "flex", gap: "8px" }}>
          <Copy size={14} aria-label="Copiar" />
          Copiar
        </Button>
      </div>

      <div style={{ 
        background: "var(--bg-muted)", 
        padding: "12px", 
        borderRadius: "var(--radius-sm)", 
        fontFamily: "monospace", 
        fontSize: "13px", 
        color: "var(--text)",
        border: "1px solid var(--border)",
        marginBottom: "16px"
      }}>
        {mcpUrl}
      </div>

      <div style={{ marginTop: "24px" }}>
        <p style={{ fontSize: "14px", fontWeight: 500, marginBottom: "8px" }}>
          Configure seu client MCP (Claude Desktop, Cursor, etc.) com:
        </p>
        <pre style={{ 
          background: "#1e1e1e", 
          color: "#d4d4d4", 
          padding: "12px", 
          borderRadius: "var(--radius-sm)", 
          fontSize: "12px", 
          overflowX: "auto",
          border: "1px solid var(--border)"
        }}>
          {JSON.stringify(configExample, null, 2)}
        </pre>
      </div>
    </Card>
  );
}
