"use client";

import React from "react";
import { MCPSetupCard } from "@/components/mcp/mcp-setup-card";
import { MCPTokenList } from "@/components/mcp/token-list";
import { MCPToolsList } from "@/components/mcp/tools-list";

export default function MCPServerPage() {
  return (
    <div style={{ 
      display: "flex", 
      flexDirection: "column", 
      gap: "24px", 
      padding: "24px",
      maxWidth: "1200px",
      margin: "0 auto",
      width: "100%"
    }}>
      <div>
        <h1 style={{ fontSize: "24px", fontWeight: 600, margin: 0 }}>Servidor MCP</h1>
        <p style={{ fontSize: "14px", color: "var(--text-secondary)", marginTop: "4px" }}>
          Gerencie o servidor MCP do Agent Portal
        </p>
      </div>

      <MCPSetupCard />

      <div>
        <h2 style={{ fontSize: "18px", fontWeight: 600, marginBottom: "16px" }}>Tokens de Acesso</h2>
        <MCPTokenList />
      </div>

      <div>
        <h2 style={{ fontSize: "18px", fontWeight: 600, marginBottom: "16px" }}>Catálogo de Ferramentas</h2>
        <MCPToolsList />
      </div>
    </div>
  );
}
