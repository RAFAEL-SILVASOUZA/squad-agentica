"use client";

import * as React from "react";
import { api, ApiError } from "@/lib/api";
import type { GitProvider, Integration, GitConnectionTestResult } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { ErrorPanel } from "@/components/ui/error-panel";

export function GitConnectionForm({ provider, connection, onClose, onSaved }: {
  provider: GitProvider;
  connection?: Integration;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = React.useState(connection?.name ?? "");
  const [organization, setOrganization] = React.useState(String(connection?.config.organization ?? ""));
  const [token, setToken] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [testBusy, setTestBusy] = React.useState(false);
  const [testResult, setTestResult] = React.useState<{ ok: boolean; message: string } | null>(null);
  // Falha no save da conexão: bloqueia a ação principal, então fica inline com retry.
  const [saveError, setSaveError] = React.useState<{ message: string; detail?: string } | null>(null);

  async function testConnection() {
    if (testBusy) return;
    const cfg: Record<string, string> = {};
    if (token.trim()) cfg.token = token.trim();
    else if (connection) cfg.token = "***";
    if (provider === "azure" && organization.trim()) cfg.organization = organization.trim();
    if (!cfg.token && !connection) { setError("Digite o token para testar."); return; }
    setTestBusy(true);
    setTestResult(null);
    setError("");
    try {
      const result = await api.post<GitConnectionTestResult>("/api/integrations/test", { type: provider, config: cfg });
      setTestResult(result.ok ? { ok: true, message: `Conectado, ${result.repositories ?? 0} repositórios` } : { ok: false, message: result.error || "Falha ao testar conexão." });
    } catch (e) {
      setTestResult({ ok: false, message: e instanceof ApiError ? e.message : "Não foi possível testar a conexão." });
    } finally { setTestBusy(false); }
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (!name.trim() || (provider === "azure" && !organization.trim()) || (!connection && !token.trim())) {
      setError("Preencha os campos obrigatórios.");
      return;
    }
    setBusy(true);
    setError("");
    setSaveError(null);
    const config = { token: token.trim() || "***", ...(provider === "azure" ? { organization: organization.trim() } : {}) };
    try {
      if (connection) await api.put(`/api/integrations/${connection.id}`, { name: name.trim(), config });
      else await api.post("/api/integrations", { type: provider, name: name.trim(), config });
      setToken("");
      onSaved();
    } catch (e) {
      setSaveError({
        message: "Não foi possível salvar a conexão",
        detail: e instanceof ApiError ? e.describe() : undefined,
      });
    } finally { setBusy(false); }
  }

  return <Modal open onClose={() => { if (!busy) onClose(); }} title={connection ? "Editar conexão" : "Nova conexão"}>
    <form onSubmit={(event) => void save(event)} style={{ display: "grid", gap: 16 }}>
      <Input label="Nome" value={name} onChange={(e) => setName(e.target.value)} required maxLength={200} disabled={busy} />
      {provider === "azure" && <Input label="Organização" value={organization} onChange={(e) => setOrganization(e.target.value)} required disabled={busy} />}
      <Input label="Token" type="password" autoComplete="new-password" value={token} onChange={(e) => setToken(e.target.value)} required={!connection} disabled={busy}
        hint={`${provider === "github" ? "PAT com escopo repo" : "Code: Read & Write"}${connection ? ". Deixe vazio para manter o token atual." : ""} O token fica criptografado e nunca é mostrado de novo.`} />
      {error && <p role="alert" style={{ color: "var(--error)" }}>{error}</p>}
      {testResult && <p role="status" style={{ fontSize: 12, color: testResult.ok ? "var(--success)" : "var(--error)" }}>{testResult.message}</p>}
      {saveError && (
        <ErrorPanel
          title={saveError.message}
          detail={saveError.detail}
          onRetry={() => void save(new Event("submit") as unknown as React.FormEvent)}
        />
      )}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <Button type="button" onClick={onClose} disabled={busy}>Cancelar</Button>
        <Button type="button" onClick={() => void testConnection()} loading={testBusy} disabled={busy}>Testar</Button>
        <Button type="submit" variant="primary" loading={busy}>Salvar conexão</Button>
      </div>
    </form>
  </Modal>;
}
