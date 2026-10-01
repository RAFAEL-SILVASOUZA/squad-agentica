"use client";

import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Card, Skeleton, EmptyState } from "@/components/ui";

interface MCPTool {
  name: string;
  description: string;
}

export function MCPToolsList() {
  const [tools, setTools] = useState<MCPTool[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const fetchTools = async () => {
    try {
      const data = await api.get<MCPTool[]>("/api/mcp/tools");
      setTools(data);
    } catch (err) {
      console.error("Erro ao carregar ferramentas MCP", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchTools();
  }, []);

  if (isLoading) {
    return (
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: "16px" }}>
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} height={100} width="100%" />
        ))}
      </div>
    );
  }

  if (tools.length === 0) {
    return (
      <EmptyState 
        title="Nenhuma ferramenta encontrada" 
        description="O servidor MCP não possui ferramentas publicadas no momento." 
      />
    );
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: "16px" }}>
      {tools.map((tool) => (
        <Card key={tool.name}>
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <span style={{ fontWeight: 600, fontSize: "14px", color: "var(--text)" }}>
              {tool.name}
            </span>
            <span style={{ fontSize: "13px", color: "var(--text-secondary)", lineHeight: "1.5" }}>
              {tool.description}
            </span>
          </div>
        </Card>
      ))}
    </div>
  );
}
