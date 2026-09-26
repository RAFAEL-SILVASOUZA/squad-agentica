"use client";

import * as React from "react";
import {
  Github,
  CheckCircle2,
  XCircle,
  RefreshCw,
  AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api";

/**
 * GitHubIntegration (fe-library).
 * - Conectar GitHub com token (campo de segredo, nunca reexibido).
 * - Status da conexão (conectado/desconectado/erro).
 * - Testar conexão.
 * - Desconectar.
 */

interface GitHubStatus {
  connected: boolean;
  username?: string;
  error?: string;
}

export function GitHubIntegration() {
  const { addToast } = useToast();
  const [status, setStatus] = React.useState<GitHubStatus | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [token, setToken] = React.useState("");
  const [connecting, setConnecting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const loadStatus = React.useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get<GitHubStatus>("/api/integrations/github/status");
      setStatus(res);
    } catch (e) {
      // Se não há integração, mostra desconectado
      setStatus({ connected: false });
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  const handleConnect = React.useCallback(async () => {
    if (!token.trim()) {
      setError("Token é obrigatório");
      return;
    }

    setConnecting(true);
    setError(null);
    try {
      await api.post("/api/integrations/github/connect", { token: token.trim() });
      addToast("success", "GitHub conectado");
      setToken("");
      await loadStatus();
    } catch (e) {
      if (e instanceof ApiError && e.details?.error) {
        setError(e.details.error as string);
      } else {
        setError(e instanceof Error ? e.message : "Erro ao conectar GitHub");
      }
    } finally {
      setConnecting(false);
    }
  }, [token, addToast, loadStatus]);

  const handleDisconnect = React.useCallback(async () => {
    try {
      await api.delete("/api/integrations/github");
      addToast("info", "GitHub desconectado");
      await loadStatus();
    } catch (e) {
      addToast("error", e instanceof Error ? e.message : "Erro ao desconectar GitHub");
    }
  }, [addToast, loadStatus]);

  const handleTest = React.useCallback(async () => {
    try {
      const res = await api.post<{ success: boolean; message?: string }>("/api/integrations/github/test");
      if (res.success) {
        addToast("success", "Conexão com GitHub OK");
      } else {
        addToast("error", res.message ?? "Falha na conexão com GitHub");
      }
    } catch (e) {
      addToast("error", e instanceof Error ? e.message : "Erro ao testar conexão");
    }
  }, [addToast]);

  if (loading) {
    return (
      <Card>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <Github size={16} aria-hidden="true" style={{ color: "var(--text-muted)" }} />
          <span style={{ fontSize: "13px", color: "var(--text-muted)" }}>Carregando status...</span>
        </div>
      </Card>
    );
  }

  return (
    <Card>
      <h3 style={{ fontSize: "14px", fontWeight: 600, color: "var(--text)", margin: "0 0 12px" }}>
        Integração GitHub
      </h3>

      {status?.connected ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <CheckCircle2 size={16} aria-hidden="true" style={{ color: "var(--success)" }} />
            <span style={{ fontSize: "13px", color: "var(--text)" }}>
              Conectado como <strong>{status.username}</strong>
            </span>
          </div>
          <div style={{ display: "flex", gap: "8px" }}>
            <Button size="sm" onClick={() => void handleTest()}>
              <RefreshCw size={13} aria-hidden="true" />
              Testar conexão
            </Button>
            <Button
              size="sm"
              onClick={() => void handleDisconnect()}
              style={{ background: "var(--error)", borderColor: "var(--error)", color: "#fff" }}
            >
              <XCircle size={13} aria-hidden="true" />
              Desconectar
            </Button>
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <XCircle size={16} aria-hidden="true" style={{ color: "var(--text-muted)" }} />
            <span style={{ fontSize: "13px", color: "var(--text-muted)" }}>Desconectado</span>
          </div>
          <Input
            id="github-token"
            label="Token GitHub"
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="ghp_xxxxxxxxxxxx"
            disabled={connecting}
            hint="O token é armazenado com segurança e nunca reexibido."
          />
          {error && (
            <p
              role="alert"
              style={{
                fontSize: "12px",
                color: "var(--error)",
                margin: 0,
                display: "flex",
                alignItems: "center",
                gap: "6px",
              }}
            >
              <AlertTriangle size={13} aria-hidden="true" />
              {error}
            </p>
          )}
          <Button size="sm" variant="primary" onClick={() => void handleConnect()} loading={connecting}>
            <Github size={13} aria-hidden="true" />
            Conectar
          </Button>
        </div>
      )}
    </Card>
  );
}
