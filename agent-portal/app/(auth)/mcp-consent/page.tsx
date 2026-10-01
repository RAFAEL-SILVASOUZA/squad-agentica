"use client";

import { Suspense, useState, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { CheckCircle, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

export default function McpConsentPage() {
  return (
    <Suspense>
      <McpConsentPageInner />
    </Suspense>
  );
}

function McpConsentPageInner() {
  const searchParams = useSearchParams();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const clientId = searchParams.get("client_id") ?? "";
  const clientName = searchParams.get("client_name") ?? clientId;
  const redirectUri = searchParams.get("redirect_uri") ?? "";
  const scope = searchParams.get("scope") ?? "";
  const codeChallenge = searchParams.get("code_challenge") ?? "";
  const codeChallengeMethod = searchParams.get("code_challenge_method") ?? "";
  const state = searchParams.get("state");
  const resource = searchParams.get("resource") ?? "";

  const buildRedirectUrl = (params: Record<string, string>): string => {
    const qs = new URLSearchParams(params).toString();
    return qs ? `${redirectUri}?${qs}` : redirectUri;
  };

  const handleAuthorize = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const res = await api.post<{ code: string }>("/api/mcp/consent", {
        client_id: clientId,
        redirect_uri: redirectUri,
        scope,
        code_challenge: codeChallenge,
        code_challenge_method: codeChallengeMethod,
        state: state ?? undefined,
        resource,
      });

      const params: Record<string, string> = { code: res.code };
      if (state) params.state = state;
      window.location.href = buildRedirectUrl(params);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Falha ao autorizar. Tente novamente.";
      setError(message);
      setLoading(false);
    }
  }, [clientId, redirectUri, scope, codeChallenge, codeChallengeMethod, state, resource]);

  const handleDeny = useCallback(() => {
    const params: Record<string, string> = { error: "access_denied" };
    if (state) params.state = state;
    window.location.href = buildRedirectUrl(params);
  }, [redirectUri, state]);

  return (
    <main
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "1.5rem",
        background: "var(--bg)",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 400,
          background: "var(--bg-card)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          padding: "2rem",
          boxShadow: "var(--shadow)",
        }}
      >
        <h1
          style={{
            fontSize: "1.25rem",
            fontWeight: 600,
            color: "var(--text)",
            margin: "0 0 0.5rem",
          }}
        >
          Consentimento MCP
        </h1>
        <p
          style={{
            fontSize: "13px",
            color: "var(--text-secondary)",
            margin: "0 0 1.5rem",
          }}
        >
          O client <strong style={{ color: "var(--text)" }}>{clientName}</strong> quer
          acessar o Agent Portal.
        </p>

        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "0.75rem",
            marginBottom: "1.5rem",
            fontSize: "13px",
          }}
        >
          {scope && (
            <div>
              <span
                style={{
                  fontWeight: 500,
                  color: "var(--text)",
                  display: "block",
                  marginBottom: "2px",
                }}
              >
                Escopo
              </span>
              <span style={{ color: "var(--text-secondary)", wordBreak: "break-all" }}>
                {scope}
              </span>
            </div>
          )}
          {redirectUri && (
            <div>
              <span
                style={{
                  fontWeight: 500,
                  color: "var(--text)",
                  display: "block",
                  marginBottom: "2px",
                }}
              >
                Redirect URI
              </span>
              <span style={{ color: "var(--text-secondary)", wordBreak: "break-all" }}>
                {redirectUri}
              </span>
            </div>
          )}
        </div>

        {error && (
          <div
            role="alert"
            style={{
              padding: "10px 14px",
              borderRadius: "var(--radius-sm)",
              background: "rgba(248, 113, 113, 0.1)",
              border: "1px solid var(--error)",
              color: "var(--error)",
              fontSize: "13px",
              marginBottom: "1rem",
            }}
          >
            {error}
          </div>
        )}

        <div style={{ display: "flex", gap: "0.75rem" }}>
          <Button
            variant="primary"
            loading={loading}
            onClick={handleAuthorize}
            style={{ flex: 1 }}
          >
            {!loading && <CheckCircle size={14} />}
            {loading ? "Autorizando..." : "Autorizar"}
          </Button>
          <Button
            onClick={handleDeny}
            disabled={loading}
            style={{ flex: 1 }}
          >
            <XCircle size={14} />
            Recusar
          </Button>
        </div>
      </div>
    </main>
  );
}
