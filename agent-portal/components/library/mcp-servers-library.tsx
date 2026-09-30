"use client";

import * as React from "react";
import {
  Server,
  Plus,
  Trash2,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { DataTable } from "@/components/ui/data-table";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api";

/**
 * MCPServersLibrary (fe-library, protótipo view-MCP-SERVERS).
 * - Grid de servidores MCP do usuário (GET /api/mcp-servers).
 * - Registrar servidor: nome, transporte (stdio/sse/http), comando/URL, env vars.
 * - Testar conexão (POST test) → popula discoveredTools.
 * - Listar tools descobertas.
 * - Excluir com confirmação.
 * - Estados: loading (skeleton), vazio (EmptyState + CTA), erro (retry).
 */

interface MCPServerItem {
  id: string;
  name: string;
  description: string;
  transport: string;
  command?: string;
  url?: string;
  env?: Record<string, string>;
  status: string;
  discoveredTools: unknown[];
  created_at: string;
  updated_at: string;
  usageCount?: number;
}

const TRANSPORT_OPTIONS = [
  { value: "stdio", label: "Stdio" },
  { value: "sse", label: "SSE" },
  { value: "http", label: "HTTP" },
];

const STATUS_LABELS: Record<string, string> = {
  disconnected: "Desconectado",
  connected: "Conectado",
  error: "Erro",
};

interface MCPFormState {
  name: string;
  description: string;
  transport: string;
  command: string;
  url: string;
  env: string;
}

const EMPTY_FORM: MCPFormState = {
  name: "",
  description: "",
  transport: "stdio",
  command: "",
  url: "",
  env: "{}",
};

function parseJsonObj(raw: string, field: string): Record<string, string> {
  const trimmed = raw.trim();
  if (!trimmed) return {};
  const parsed = JSON.parse(trimmed);
  if (typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${field} deve ser um objeto JSON`);
  }
  return parsed;
}

export function MCPServersLibrary() {
  const { addToast } = useToast();
  const [servers, setServers] = React.useState<MCPServerItem[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const [modalOpen, setModalOpen] = React.useState(false);
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [form, setForm] = React.useState<MCPFormState>(EMPTY_FORM);
  const [formError, setFormError] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);

  const [deleting, setDeleting] = React.useState<MCPServerItem | null>(null);
  const [deleteBusy, setDeleteBusy] = React.useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = React.useState(false);

  const [testing, setTesting] = React.useState<MCPServerItem | null>(null);
  const [testBusy, setTestBusy] = React.useState(false);
  const [testResult, setTestResult] = React.useState<{ success: boolean; message?: string; tools?: unknown[] } | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.list<MCPServerItem>("/api/mcp-servers", { page: 1, limit: 100 });
      setServers(res.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao carregar servidores MCP");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const openCreate = React.useCallback(() => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setModalOpen(true);
  }, []);

  const openEdit = React.useCallback((server: MCPServerItem) => {
    setEditingId(server.id);
    setForm({
      name: server.name,
      description: server.description,
      transport: server.transport,
      command: server.command ?? "",
      url: server.url ?? "",
      env: JSON.stringify(server.env ?? {}, null, 2),
    });
    setFormError(null);
    setModalOpen(true);
  }, []);

  const handleSave = React.useCallback(async () => {
    setFormError(null);

    let env: Record<string, string>;
    try {
      env = parseJsonObj(form.env, "Env");
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "JSON inválido");
      return;
    }

    if (!form.name.trim()) {
      setFormError("Nome é obrigatório");
      return;
    }

    const body: Record<string, unknown> = {
      name: form.name.trim(),
      description: form.description.trim(),
      transport: form.transport,
      env,
    };

    if (form.transport === "stdio") {
      if (!form.command.trim()) {
        setFormError("Comando é obrigatório para transporte stdio");
        return;
      }
      body.command = form.command.trim();
    } else {
      if (!form.url.trim()) {
        setFormError("URL é obrigatória para transporte SSE/HTTP");
        return;
      }
      body.url = form.url.trim();
    }

    setSaving(true);
    try {
      if (editingId) {
        await api.put(`/api/mcp-servers/${editingId}`, body);
        addToast("success", "Servidor MCP atualizado");
      } else {
        await api.post("/api/mcp-servers", body);
        addToast("success", "Servidor MCP registrado");
      }
      setModalOpen(false);
      await load();
    } catch (e) {
      if (e instanceof ApiError && e.details?.errors) {
        setFormError(JSON.stringify(e.details.errors));
      } else {
        setFormError(e instanceof Error ? e.message : "Erro ao salvar servidor MCP");
      }
    } finally {
      setSaving(false);
    }
  }, [form, editingId, addToast, load]);

  const handleDelete = React.useCallback(async () => {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      await api.delete(`/api/mcp-servers/${deleting.id}`);
      addToast("info", "Servidor MCP excluído");
      setDeleting(null);
      setDeleteModalOpen(false);
      await load();
    } catch (e) {
      addToast("error", e instanceof Error ? e.message : "Erro ao excluir servidor MCP");
    } finally {
      setDeleteBusy(false);
    }
  }, [deleting, addToast, load]);

  const handleTest = React.useCallback(async () => {
    if (!testing) return;
    setTestBusy(true);
    setTestResult(null);
    try {
      // Contrato: 200 { status: "connected"|"error", discoveredTools, error? }.
      // A tela lia { success, tools } e mostrava "Falha" mesmo conectando.
      const res = await api.post<{
        status: string;
        discoveredTools?: { name: string; description?: string }[];
        error?: string | null;
      }>(`/api/mcp-servers/${testing.id}/test`);
      const success = res.status === "connected";
      const tools = res.discoveredTools ?? [];
      setTestResult({ success, message: success ? undefined : res.error ?? undefined, tools });
      if (success) addToast("success", `${tools.length} tools descobertas`);
      await load();
    } catch (e) {
      setTestResult({ success: false, message: e instanceof Error ? e.message : "Erro ao testar conexão" });
    } finally {
      setTestBusy(false);
    }
  }, [testing, addToast, load]);

  // ─── Content ──────────────────────────────────────────────────────────────
  let content: React.ReactNode;

  if (loading) {
    content = (
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
          gap: "12px",
        }}
      >
        {[0, 1, 2, 3].map((i) => (
          <Card key={i}>
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              <Skeleton width="60%" height={16} />
              <Skeleton width="90%" height={12} />
              <Skeleton width="40%" height={12} />
            </div>
          </Card>
        ))}
      </div>
    );
  } else if (error) {
    content = (
      <Card>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "12px",
            flexWrap: "wrap",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <AlertTriangle size={16} aria-hidden="true" style={{ color: "var(--error)" }} />
            <span style={{ fontSize: "13px", color: "var(--error)" }}>{error}</span>
          </div>
          <Button size="sm" onClick={() => void load()}>
            <RefreshCw size={13} aria-hidden="true" />
            Tentar novamente
          </Button>
        </div>
      </Card>
    );
  } else if (servers.length === 0) {
    content = (
      <EmptyState
        icon={Server}
        title="Nenhum servidor MCP ainda"
        description="Servidores MCP expõem tools externas que os agentes podem usar."
        action={
          <Button variant="primary" onClick={openCreate}>
            <Plus size={14} aria-hidden="true" />
            Registrar primeiro servidor
          </Button>
        }
      />
    );
  } else {
    content = (
      <div>
        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            marginBottom: "16px",
          }}
        >
          <Button variant="primary" size="sm" onClick={openCreate}>
            <Plus size={14} aria-hidden="true" />
            Novo servidor
          </Button>
        </div>

        <DataTable<MCPServerItem>
          columns={[
            { key: "name", header: "Nome", sortable: true },
            {
              key: "status",
              header: "Status",
              sortable: true,
              render: (s) =>
                s.status === "connected"
                  ? `Conectado · ${s.discoveredTools.length} tools`
                  : STATUS_LABELS[s.status] ?? s.status,
            },
            { key: "description", header: "Descrição", render: (s) => s.description || "—" },
            { key: "transport", header: "Transporte", sortable: true },
            { key: "usageCount", header: "Usos", sortable: true, render: (s) => `${s.usageCount ?? 0} agentes` },
          ]}
          rows={servers}
          rowKey={(s) => s.id}
          searchPlaceholder="Buscar servidores…"
          onRowMenu={(server, action) => {
            if (action === "edit") openEdit(server);
            if (action === "test") {
              setTesting(server);
              setTestResult(null);
            }
            if (action === "delete") {
              setDeleting(server);
              setDeleteModalOpen(true);
            }
          }}
          rowMenuItems={[
            { label: "Editar", action: "edit" },
            { label: "Testar conexão", action: "test" },
            { label: "Excluir", action: "delete", danger: true },
          ]}
          emptyMessage="Nenhum servidor encontrado"
        />
      </div>
    );
  }

  return (
    <div>
      {content}

      {/* Modal criar/editar */}
      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editingId ? "Editar servidor MCP" : "Novo servidor MCP"}
        footer={
          <>
            <Button size="sm" onClick={() => setModalOpen(false)} disabled={saving}>
              Cancelar
            </Button>
            <Button size="sm" variant="primary" onClick={() => void handleSave()} loading={saving}>
              {editingId ? "Salvar alterações" : "Registrar servidor"}
            </Button>
          </>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          <Input
            id="mcp-name"
            label="Nome"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            placeholder="Ex.: Servidor de busca"
            disabled={saving}
          />
          <Input
            id="mcp-description"
            label="Descrição"
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            placeholder="O que este servidor MCP faz"
            disabled={saving}
          />
          <Select
            id="mcp-transport"
            label="Transporte"
            value={form.transport}
            options={TRANSPORT_OPTIONS}
            onChange={(e) => setForm((f) => ({ ...f, transport: e.target.value }))}
            disabled={saving}
          />
          {form.transport === "stdio" ? (
            <Input
              id="mcp-command"
              label="Comando"
              value={form.command}
              onChange={(e) => setForm((f) => ({ ...f, command: e.target.value }))}
              placeholder="Ex.: npx @modelcontextprotocol/server-filesystem"
              disabled={saving}
            />
          ) : (
            <Input
              id="mcp-url"
              label="URL"
              value={form.url}
              onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
              placeholder="Ex.: http://localhost:3001/sse"
              disabled={saving}
            />
          )}
          <Textarea
            id="mcp-env"
            label="Env vars (JSON)"
            value={form.env}
            onChange={(e) => setForm((f) => ({ ...f, env: e.target.value }))}
            rows={3}
            placeholder='{"API_KEY": "valor"}'
            disabled={saving}
            style={{ fontFamily: "var(--font-mono)", fontSize: "12px" }}
          />
          {formError && (
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
              {formError}
            </p>
          )}
        </div>
      </Modal>

      {/* Modal testar conexão */}
      <Modal
        open={!!testing}
        onClose={() => setTesting(null)}
        title={`Testar ${testing?.name ?? ""}`}
        footer={
          <>
            <Button size="sm" onClick={() => setTesting(null)} disabled={testBusy}>
              Fechar
            </Button>
            <Button size="sm" variant="primary" onClick={() => void handleTest()} loading={testBusy}>
              Testar conexão
            </Button>
          </>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          {testResult ? (
            <div
              style={{
                padding: "12px",
                borderRadius: "var(--radius-sm)",
                background: testResult.success ? "var(--success-bg)" : "var(--error-bg)",
                border: `1px solid ${testResult.success ? "var(--success)" : "var(--error)"}`,
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  marginBottom: "8px",
                }}
              >
                {testResult.success ? (
                  <CheckCircle2 size={16} aria-hidden="true" style={{ color: "var(--success)" }} />
                ) : (
                  <XCircle size={16} aria-hidden="true" style={{ color: "var(--error)" }} />
                )}
                <span
                  style={{
                    fontSize: "13px",
                    fontWeight: 600,
                    color: testResult.success ? "var(--success)" : "var(--error)",
                  }}
                >
                  {testResult.success ? "Conectado" : "Falha na conexão"}
                </span>
              </div>
              {testResult.message && (
                <p style={{ fontSize: "12px", color: "var(--text-secondary)", margin: 0 }}>
                  {testResult.message}
                </p>
              )}
              {testResult.tools && testResult.tools.length > 0 && (
                <div style={{ marginTop: "10px" }}>
                  <strong style={{ fontSize: "12px", color: "var(--text)" }}>
                    Tools descobertas ({testResult.tools.length}):
                  </strong>
                  <ul style={{ margin: "6px 0 0", paddingLeft: "18px", fontSize: "12px", color: "var(--text-secondary)" }}>
                    {testResult.tools.map((tool, i) => (
                      <li key={i}>
                        {typeof tool === "object" && tool && "name" in tool
                          ? `${(tool as { name: string }).name}${(tool as { description?: string }).description ? ` — ${(tool as { description?: string }).description}` : ""}`
                          : JSON.stringify(tool)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <p style={{ fontSize: "13px", color: "var(--text-secondary)", margin: 0 }}>
              Clique em &quot;Testar conexão&quot; para verificar se o servidor está acessível e descobrir as tools disponíveis.
            </p>
          )}
        </div>
      </Modal>

      {/* Modal confirmar exclusão */}
      <Modal
        open={deleteModalOpen}
        onClose={() => setDeleteModalOpen(false)}
        title="Excluir servidor MCP"
        footer={
          <>
            <Button size="sm" onClick={() => setDeleting(null)} disabled={deleteBusy}>
              Cancelar
            </Button>
            <Button
              size="sm"
              onClick={() => void handleDelete()}
              loading={deleteBusy}
              style={{ background: "var(--error-strong)", borderColor: "var(--error-strong)", color: "#fff" }}
            >
              <Trash2 size={13} aria-hidden="true" />
              Excluir
            </Button>
          </>
        }
      >
        <p style={{ fontSize: "13px", color: "var(--text)", margin: 0 }}>
          Excluir o servidor MCP <strong>{deleting?.name}</strong>? Agentes que o referenciam
          precisarão ser atualizados.
        </p>
      </Modal>
    </div>
  );
}
