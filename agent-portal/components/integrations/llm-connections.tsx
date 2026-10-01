"use client";

import * as React from "react";
import { api, ApiError } from "@/lib/api";
import type { Integration } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { DataTable, type DataTableColumn, type DataTableRowMenuItem } from "@/components/ui/data-table";
import { Modal } from "@/components/ui/modal";
import { useToast } from "@/components/ui/toast";
import { LlmConnectionForm } from "./llm-connection-form";

/** Junta nomes em lista pt-BR: "A", "A e B", "A, B e C". */
function joinNamesPtBr(names: string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} e ${names[names.length - 1]}`;
}

/** Extrai os ids de modelo do config de uma integração LLM. */
function modelsOf(config: Record<string, unknown>): string[] {
  const models = config.models;
  if (Array.isArray(models)) return models.map((m) => String(m)).filter(Boolean);
  const single = config.model;
  return typeof single === "string" && single ? [single] : [];
}

/**
 * Lista e gerencia integrações LLM (adendo 8).
 *
 * - Criação/edição via LlmConnectionForm (modal), com teste de conexão inline.
 * - A chave de API nunca é devolvida pela API; a tabela mostra só o hint.
 * - Exclusão com confirmação em modal (sem window.confirm).
 */
export function LlmConnections() {
  const { addToast } = useToast();
  const [connections, setConnections] = React.useState<Integration[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  const [editing, setEditing] = React.useState<Integration | null | undefined>();
  const [deleting, setDeleting] = React.useState<Integration | null>(null);
  const [deleteError, setDeleteError] = React.useState("");
  const [deleteBusy, setDeleteBusy] = React.useState(false);

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
      setConnections(items.filter((item) => item.type === "llm"));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Não foi possível carregar as conexões LLM.");
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
      addToast("success", "Conexão LLM excluída");
      await load();
    } catch (e) {
      setDeleteError(e instanceof ApiError ? e.message : "Não foi possível excluir a conexão. Feche e tente novamente.");
    } finally {
      setDeleteBusy(false);
    }
  }

  const columns: DataTableColumn<Integration>[] = [
    { key: "name", header: "Nome", sortable: true, render: (row) => <span style={{ fontWeight: 600 }}>{row.name}</span> },
    { key: "provider", header: "Provedor", render: (row) => <span style={{ fontSize: 12 }}>{String(row.config.provider_kind ?? "—")}</span> },
    { key: "models", header: "Modelos", render: (row) => {
      const models = modelsOf(row.config);
      return models.length ? <span style={{ fontSize: 12 }}>{joinNamesPtBr(models)}</span> : <span style={{ color: "var(--text-muted)" }}>—</span>;
    }},
    { key: "apiKeyHint", header: "Chave", render: (row) => row.apiKeyHint ? <code style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>{row.apiKeyHint}</code> : <span style={{ color: "var(--text-muted)" }}>—</span> },
  ];

  const rowMenuItems: DataTableRowMenuItem[] = [
    { label: "Editar", action: "edit" },
    { label: "Excluir", action: "delete", danger: true },
  ];

  function handleRowMenu(row: Integration, action: string) {
    if (action === "edit") setEditing(row);
    else if (action === "delete") setDeleting(row);
  }

  if (loading) return <p role="status">Carregando conexões LLM...</p>;
  if (error) return <div><p role="alert">{error}</p><Button onClick={() => void load()}>Tentar novamente</Button></div>;

  return <div style={{ display: "grid", gap: 16 }}>
    <div><Button variant="primary" onClick={() => setEditing(null)}>Nova conexão LLM</Button></div>
    <DataTable
      columns={columns}
      rows={connections}
      rowKey={(row) => row.id}
      searchPlaceholder="Buscar conexões LLM…"
      onRowMenu={handleRowMenu}
      rowMenuItems={rowMenuItems}
      emptyMessage="Nenhuma conexão LLM cadastrada."
    />
    {editing !== undefined && <LlmConnectionForm connection={editing ?? undefined} onClose={() => setEditing(undefined)} onSaved={() => { setEditing(undefined); addToast("success", "Conexão LLM salva"); void load(); }} />}
    <Modal open={!!deleting} title="Excluir conexão LLM" onClose={() => { if (!deleteBusy) setDeleting(null); }} footer={<>
      <Button disabled={deleteBusy} onClick={() => setDeleting(null)}>Cancelar</Button>
      <Button disabled={!!deleteError} loading={deleteBusy} onClick={() => void remove()}>Excluir conexão</Button>
    </>}>
      <p>Excluir a conexão {deleting?.name}?</p>
      {deleteError && <p role="alert">{deleteError}</p>}
    </Modal>
  </div>;
}
