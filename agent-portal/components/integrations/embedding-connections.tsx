"use client";

import * as React from "react";
import { api, ApiError } from "@/lib/api";
import type { Integration } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable, type DataTableColumn, type DataTableRowMenuItem } from "@/components/ui/data-table";
import { Modal } from "@/components/ui/modal";
import { useToast } from "@/components/ui/toast";
import { EmbeddingConnectionForm } from "./embedding-connection-form";

/**
 * Lista e gerencia integrações de embedding (adendo 9).
 *
 * Cadastro separado da conexão LLM: cada conexão de embedding tem a própria
 * base_url, api_key e modelo. Criação/edição via EmbeddingConnectionForm
 * (modal), com teste de conexão inline. A chave de API nunca é devolvida pela
 * API; a tabela mostra só o hint. Exclusão com confirmação em modal.
 */
export function EmbeddingConnections() {
  const { addToast } = useToast();
  const [connections, setConnections] = React.useState<Integration[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  const [editing, setEditing] = React.useState<Integration | null | undefined>();
  const [deleting, setDeleting] = React.useState<Integration | null>(null);
  const [deleteError, setDeleteError] = React.useState("");
  const [deleteBusy, setDeleteBusy] = React.useState(false);
  const [defaultEmbeddingId, setDefaultEmbeddingId] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const items: Integration[] = [];
      let page = 1;
      while (true) {
        const res = await api.list<Integration>("/api/integrations", { page, limit: 100 });
        items.push(...res.items);
        if (!res.items.length || items.length >= res.total) break;
        page++;
      }
      setConnections(items.filter((item) => item.type === "embedding"));
      const prefs = await api.get<{ defaultEmbeddingIntegrationId?: string | null }>("/api/auth/preferences");
      setDefaultEmbeddingId(prefs.defaultEmbeddingIntegrationId ?? null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Não foi possível carregar as conexões de embedding.");
    } finally {
      setLoading(false);
    }
  }, []);
  React.useEffect(() => {
    void load();
  }, [load]);

  async function remove() {
    if (!deleting || deleteBusy) return;
    setDeleteBusy(true);
    setDeleteError("");
    try {
      await api.delete(`/api/integrations/${deleting.id}`);
      setDeleting(null);
      addToast("success", "Conexão de embedding excluída");
      await load();
    } catch (e) {
      setDeleteError(e instanceof ApiError ? e.message : "Não foi possível excluir a conexão. Feche e tente novamente.");
    } finally {
      setDeleteBusy(false);
    }
  }

  /** Define a conexão como padrão de embedding. */
  async function setDefault(row: Integration) {
    try {
      await api.put("/api/auth/preferences", { default_embedding_integration_id: row.id });
      setDefaultEmbeddingId(row.id);
      addToast("success", "Conexão definida como padrão de embedding");
    } catch (e) {
      addToast("error", e instanceof ApiError ? e.message : "Não foi possível definir o padrão.");
    }
  }

  const columns: DataTableColumn<Integration>[] = [
    { key: "name", header: "Nome", sortable: true, render: (row) => (
      <span style={{ fontWeight: 600, display: "inline-flex", alignItems: "center", gap: 6 }}>
        {row.name}
        {row.id === defaultEmbeddingId && <Badge status="success" label="Padrão" />}
      </span>
    ) },
    { key: "provider", header: "Provedor", render: (row) => <span style={{ fontSize: 12 }}>{String(row.config.provider_kind ?? "—")}</span> },
    { key: "model", header: "Modelo", render: (row) => {
      const model = row.config.model;
      return typeof model === "string" && model ? <span style={{ fontSize: 12 }}>{model}</span> : <span style={{ color: "var(--text-muted)" }}>—</span>;
    }},
    { key: "baseUrl", header: "Base URL", render: (row) => {
      const url = row.config.base_url;
      return typeof url === "string" && url ? <span style={{ fontSize: 12 }}>{url}</span> : <span style={{ color: "var(--text-muted)" }}>—</span>;
    }},
    { key: "apiKeyHint", header: "Chave", render: (row) => row.apiKeyHint ? <code style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>{row.apiKeyHint}</code> : <span style={{ color: "var(--text-muted)" }}>—</span> },
  ];

  const rowMenuItems: DataTableRowMenuItem[] = [
    { label: "Editar", action: "edit" },
    { label: "Definir como padrão", action: "default" },
    { label: "Excluir", action: "delete", danger: true },
  ];

  function handleRowMenu(row: Integration, action: string) {
    if (action === "edit") setEditing(row);
    else if (action === "delete") setDeleting(row);
    else if (action === "default") void setDefault(row);
  }

  if (loading) return <p role="status">Carregando conexões de embedding...</p>;
  if (error) return <div><p role="alert">{error}</p><Button onClick={() => void load()}>Tentar novamente</Button></div>;

  return <div style={{ display: "grid", gap: 16 }}>
    <div><Button variant="primary" onClick={() => setEditing(null)}>Nova conexão de embedding</Button></div>
    <DataTable
      columns={columns}
      rows={connections}
      rowKey={(row) => row.id}
      searchPlaceholder="Buscar conexões de embedding…"
      onRowMenu={handleRowMenu}
      rowMenuItems={rowMenuItems}
      emptyMessage="Nenhuma conexão de embedding cadastrada."
    />
    {editing !== undefined && <EmbeddingConnectionForm connection={editing ?? undefined} onClose={() => setEditing(undefined)} onSaved={() => { setEditing(undefined); addToast("success", "Conexão de embedding salva"); void load(); }} />}
    <Modal open={!!deleting} title="Excluir conexão de embedding" onClose={() => { if (!deleteBusy) setDeleting(null); }} footer={<>
      <Button disabled={deleteBusy} onClick={() => setDeleting(null)}>Cancelar</Button>
      <Button disabled={!!deleteError} loading={deleteBusy} onClick={() => void remove()}>Excluir conexão</Button>
    </>}>
      <p>Excluir a conexão {deleting?.name}?</p>
      {deleteError && <p role="alert">{deleteError}</p>}
    </Modal>
  </div>;
}
