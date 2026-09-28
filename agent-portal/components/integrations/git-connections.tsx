"use client";

import * as React from "react";
import { api, ApiError } from "@/lib/api";
import type { GitProvider, Integration, GitConnectionTestResult } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Modal } from "@/components/ui/modal";
import { useToast } from "@/components/ui/toast";
import { GitConnectionForm } from "./git-connection-form";

interface PipelineUsage { id: string; name: string; repository?: { integrationId: string } | null }

/** Junta nomes em lista pt-BR: "A", "A e B", "A, B e C". */
function joinNamesPtBr(names: string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} e ${names[names.length - 1]}`;
}

export function GitConnections({ provider }: { provider: GitProvider }) {
  const { addToast } = useToast();
  const [connections, setConnections] = React.useState<Integration[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  const [editing, setEditing] = React.useState<Integration | null | undefined>();
  const [results, setResults] = React.useState<Record<string, string>>({});
  const [testing, setTesting] = React.useState<Record<string, boolean>>({});
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
      setResults((prev) => ({ ...prev, [connection.id]: result.ok ? `Conectado, ${result.repositories ?? 0} repositórios` : result.error || "Falha ao testar conexão." }));
    } catch (e) { setResults((prev) => ({ ...prev, [connection.id]: e instanceof ApiError ? e.message : "Não foi possível testar a conexão." })); }
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

  return <div style={{ display: "grid", gap: 16 }}>
    <div><Button variant="primary" onClick={() => setEditing(null)}>Nova conexão</Button></div>
    {loading ? <p role="status">Carregando conexões...</p> : error ? <Card><p role="alert">{error}</p><Button onClick={() => void load()}>Tentar novamente</Button></Card> : connections.length === 0 ? <Card>Nenhuma conexão cadastrada.</Card> : connections.map((connection) => <Card key={connection.id}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 16, justifyContent: "space-between", alignItems: "center" }}>
        <div><h2 style={{ margin: "0 0 4px", fontSize: 16, overflowWrap: "anywhere" }}>{connection.name}</h2><span>{connection.status === "active" ? "Ativa" : "Desativada"}</span></div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          <Button aria-label={`Testar conexão ${connection.name}`} loading={testing[connection.id]} onClick={() => void test(connection)}>Testar conexão</Button>
          <Button aria-label={`Editar ${connection.name}`} onClick={() => setEditing(connection)}>Editar</Button>
          <Button aria-label={`Excluir ${connection.name}`} onClick={() => void prepareDelete(connection)}>Excluir</Button>
        </div>
      </div>
      {results[connection.id] && <p role="status">{results[connection.id]}</p>}
    </Card>)}
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
