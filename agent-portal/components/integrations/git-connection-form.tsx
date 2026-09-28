"use client";

import * as React from "react";
import { api, ApiError } from "@/lib/api";
import type { GitProvider, Integration } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";

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

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (!name.trim() || (provider === "azure" && !organization.trim()) || (!connection && !token.trim())) {
      setError("Preencha os campos obrigatórios.");
      return;
    }
    setBusy(true);
    setError("");
    const config = { token: token.trim() || "***", ...(provider === "azure" ? { organization: organization.trim() } : {}) };
    try {
      if (connection) await api.put(`/api/integrations/${connection.id}`, { name: name.trim(), config });
      else await api.post("/api/integrations", { type: provider, name: name.trim(), config });
      setToken("");
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Não foi possível salvar a conexão. Confira os dados e tente novamente.");
    } finally { setBusy(false); }
  }

  return <Modal open onClose={() => { if (!busy) onClose(); }} title={connection ? "Editar conexão" : "Nova conexão"}>
    <form onSubmit={(event) => void save(event)} style={{ display: "grid", gap: 16 }}>
      <Input label="Nome" value={name} onChange={(e) => setName(e.target.value)} required maxLength={200} disabled={busy} />
      {provider === "azure" && <Input label="Organização" value={organization} onChange={(e) => setOrganization(e.target.value)} required disabled={busy} />}
      <Input label="Token" type="password" autoComplete="new-password" value={token} onChange={(e) => setToken(e.target.value)} required={!connection} disabled={busy}
        hint={`${provider === "github" ? "PAT com escopo repo" : "Code: Read & Write"}${connection ? ". Deixe vazio para manter o token atual." : ""}`} />
      {error && <p role="alert" style={{ color: "var(--error)" }}>{error}</p>}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <Button type="button" onClick={onClose} disabled={busy}>Cancelar</Button>
        <Button type="submit" variant="primary" loading={busy}>Salvar conexão</Button>
      </div>
    </form>
  </Modal>;
}
