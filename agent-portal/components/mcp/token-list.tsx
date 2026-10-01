"use client";

import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { 
  Table, 
  Badge, 
  Button, 
  Skeleton, 
  EmptyState, 
  useToast 
} from "@/components/ui";

interface MCPToken {
  jti: string;
  client_name: string;
  scope: string;
  created_at: string;
  expires_at: string;
  revoked_at: string | null;
}

export function MCPTokenList() {
  const { addToast } = useToast();
  const [tokens, setTokens] = useState<MCPToken[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const fetchTokens = async () => {
    try {
      const data = await api.get<MCPToken[]>("/api/mcp/tokens");
      setTokens(data);
    } catch (err) {
      addToast("error", "Falha ao carregar tokens do servidor MCP.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchTokens();
  }, []);

  const handleRevoke = async (jti: string) => {
    try {
      await api.delete(`/api/mcp/tokens/${jti}`);
      addToast("success", "Token revogado com sucesso.");
      await fetchTokens();
    } catch (err) {
      addToast("error", "Falha ao revogar token.");
    }
  };

  if (isLoading) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        <Skeleton height={40} width="100%" />
        <Skeleton height={40} width="100%" />
        <Skeleton height={40} width="100%" />
      </div>
    );
  }

  if (tokens.length === 0) {
    return (
      <EmptyState 
        title="Nenhum token encontrado" 
        description="Não existem tokens de acesso configurados para o servidor MCP." 
      />
    );
  }

  const columns: import("@/components/ui").TableColumn<MCPToken>[] = [
    { key: "client_name", header: "Client", render: (t) => t.client_name },
    { key: "scope", header: "Escopo", render: (t) => t.scope },
    { key: "created_at", header: "Criado em", render: (t) => new Date(t.created_at).toLocaleString() },
    { key: "expires_at", header: "Expira em", render: (t) => new Date(t.expires_at).toLocaleString() },
    { 
      key: "status", 
      header: "Status", 
      render: (t) => (
        <Badge status={t.revoked_at === null ? "success" : "neutral"} label={t.revoked_at === null ? "Ativo" : "Revogado"} />
      ) 
    },
    { 
      key: "actions", 
      header: "Ações", 
      render: (t) => (
        <Button 
          size="sm" 
          variant="default" 
          disabled={t.revoked_at !== null} 
          onClick={() => handleRevoke(t.jti)}
          style={{ color: "var(--text-danger)" }}
        >
          Revogar
        </Button>
      ) 
    },
  ];

  return (
    <Table data={tokens} columns={columns} rowKey={(t) => t.jti} />
  );
}
