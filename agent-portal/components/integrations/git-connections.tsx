"use client";

import * as React from "react";
import { api, ApiError } from "@/lib/api";
import type { GitProvider, Integration, GitConnectionTestResult } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { DataTable, type DataTableColumn, type DataTableRowMenuItem } from "@/components/ui/data-table";
import { Modal } from "@/components/ui/modal";
import { useToast } from "@/components/ui/toast";
import { relativeTime } from "@/lib/relative-time";
import { GitConnectionForm } from "./git-connection-form";

interface PipelineUsage { id: string; name: string; repository?: { integrationId: string } | null }

/** Junta nomes em lista pt-BR: "A", "A e B", "A, B e C". */
function joinNamesPtBr(names: string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} e ${names[names.length - 1]}`;
}

function formatTestStatus(lastTestStatus: string | null | undefined, lastTestedAt: string | null | undefined): string {
  if (!lastTestStatus) return "Nunca testado";
  const when = lastTestedAt ? relativeTime(lastTestedAt) : "";
  if (lastTestStatus === "ok") return `● válido · ${when}`;
  return `● falhou · ${when}`;
}

export function GitConnections({ provider }: { provider: GitProvider }) {
  const { addToast } = useToast();
  const [connections, setConnections] = React.useState<Integration[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  const [editing, setEditing] = React.useState<Integration | null | undefined>();
  const [testing, setTesting] = React.useState<Record<string, boolean>>({});
  const [testResults, setTestResults] = React.useState<Record<string, string>>({});
  const [deleting, setDeleting] = React.useState<Integration | null>(null);
  const [pipelines, setPipelines] = React.useState<PipelineUsage[]>([]);
  const [usageLoading, setUsageLoading] = React.useState(false);
  const [deleteError, setDeleteError] = React.useState("");
  const [deleteBusy, setDeleteBusy] = React.useState(false);
  const deletionRequest = React.useRef(0);

  const load = React.useCallback(async () => {
    setLoading(true); setError("");
    try {
      const items: Integration[] = [];
      let page = 1;
      while (true) {
        const res = await api.list<Integration>("/api/integrations", { page, limit: 100 });
        items.push(...res.items);
        if (!res.items.length || items.length >= res.total) break;
        page++;
      }
      setConnections(items.filter((item) => item.type === provider));
    } catch (e) { setError(e instanceof ApiError ? e.message : "Não foi possível carregar as conexões."); }
    finally { setLoading(false); }
  }, [provider]);
  React.useEffect(() => { void load(); }, [load]);

  async function test(connection: Integration) {
    setTesting((prev) => ({ ...prev, [connection.id]: true }));
    try {
      const result = await api.post<GitConnectionTestResult>(`/api/integrations/${connection.id}/test`);
      setTestResults((prev) => ({ ...prev, [connection.id]: result.ok ? `Conectado, ${result.repositories ?? 0} repositórios` : result.error || "Falha ao testar conexão." }));
      void load();
    } catch (e) { setTestResults((prev) => ({ ...prev, [connection.id]: e instanceof ApiError ? e.message : "Não foi possível testar a conexão." })); }
    finally { setTesting((prev) => ({ ...prev, [connection.id]: false })); }
  }

  async function prepareDelete(connection: Integration) {
    const request = ++deletionRequest.current;
    setDeleting(connection); setPipelines([]); setDeleteError(""); setUsageLoading(true);
    try {
      const items: PipelineUsage[] = [];
      let page = 1;
      while (true) {
        const res = await api.list<PipelineUsage>("/api/pipelines", { page, limit: 100 });
        items.push(...res.items);
        if (!res.items.length || items.length >= res.total) break;
        page++;
      }
      if (request === deletionRequest.current) setPipelines(items.filter((item) => item.repository?.integrationId === connection.id));
    } catch (e) { if (request === deletionRequest.current) setDeleteError(e instanceof ApiError ? e.message : "Não foi possível verificar os pipelines. Feche e tente novamente."); }
    finally { if (request === deletionRequest.current) setUsageLoading(false); }
  }

  async function remove() {
    if (!deleting || deleteBusy || usageLoading || deleteError) return;
    setDeleteBusy(true);
    try {
      await api.delete(`/api/integrations/${deleting.id}`);
      setDeleting(null); addToast("success", "Conexão excluída"); await load();
    } catch (e) { setDeleteError(e instanceof ApiError ? e.message : "Não foi possível excluir a conexão. Feche e tente novamente."); }
    finally { setDeleteBusy(false); }
  }

  const columns: DataTableColumn<Integration>[] = [
    { key: "name", header: "Nome", sortable: true, render: (row) => <span style={{ fontWeight: 600 }}>{row.name}</span> },
    { key: "tokenHint", header: "Token", render: (row) => row.tokenHint ? <code style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>{row.tokenHint}</code> : <span style={{ color: "var(--text-muted)" }}>—</span> },
    { key: "lastTestStatus", header: "Status", render: (row) => {
      const status = formatTestStatus(row.lastTestStatus, row.lastTestedAt);
      const color = row.lastTestStatus === "ok" ? "var(--success)" : row.lastTestStatus === "failed" ? "var(--error)" : "var(--text-muted)";
      return <span style={{ color, fontSize: 12 }}>{status}</span>;
    }},
    { key: "usageCount", header: "Usos", render: (row) => <span style={{ fontSize: 12 }}>{row.usageCount} pipeline{row.usageCount !== 1 ? "s" : ""}</span> },
  ];

  const rowMenuItems: DataTableRowMenuItem[] = [
    { label: "Testar", action: "test" },
    { label: "Editar", action: "edit" },
    { label: "Excluir", action: "delete", danger: true },
  ];

  function handleRowMenu(row: Integration, action: string) {
    if (action === "test") void test(row);
    else if (action === "edit") setEditing(row);
    else if (action === "delete") void prepareDelete(row);
  }

  if (loading) return <p role="status">Carregando conexões...</p>;
  if (error) return <div><p role="alert">{error}</p><Button onClick={() => void load()}>Tentar novamente</Button></div>;

  return <div style={{ display: "grid", gap: 16 }}>
    <div><Button variant="primary" onClick={() => setEditing(null)}>Nova conexão</Button></div>
    <DataTable
      columns={columns}
      rows={connections}
      rowKey={(row) => row.id}
      searchPlaceholder="Buscar conexões…"
      onRowMenu={handleRowMenu}
      rowMenuItems={rowMenuItems}
      emptyMessage="Nenhuma conexão cadastrada."
    />
    {Object.entries(testResults).map(([id, msg]) => (
      <p key={id} role="status" style={{ fontSize: 12, color: "var(--text-secondary)" }}>{msg}</p>
    ))}
    {editing !== undefined && <GitConnectionForm provider={provider} connection={editing ?? undefined} onClose={() => setEditing(undefined)} onSaved={() => { setEditing(undefined); addToast("success", "Conexão salva"); void load(); }} />}
    <Modal open={!!deleting} title="Excluir conexão" onClose={() => { if (!deleteBusy) { deletionRequest.current++; setDeleting(null); } }} footer={<>
      <Button disabled={deleteBusy} onClick={() => { deletionRequest.current++; setDeleting(null); }}>Cancelar</Button>
      <Button disabled={usageLoading || !!deleteError} loading={deleteBusy} onClick={() => void remove()}>Excluir conexão</Button>
    </>}>
      <p>Excluir a conexão {deleting?.name}?</p>
      {usageLoading ? <p role="status">Verificando pipelines...</p> : deleteError ? <p role="alert">{deleteError}</p> : pipelines.length === 1 ? <p>O pipeline {pipelines[0].name} ficará sem repositório.</p> : pipelines.length > 1 ? <p>Os pipelines {joinNamesPtBr(pipelines.map((item) => item.name))} ficarão sem repositório.</p> : <p>Nenhum pipeline usa esta conexão.</p>}
    </Modal>
  </div>;
}
