"use client";

import * as React from "react";
import {
  Wrench,
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
 * ToolsEditor (fe-library, protótipo view-TOOLS-CUSTOM).
 * - Grid de tools custom do usuário (GET /api/tools).
 * - Criar/editar via modal: nome, descrição, script (Python/JS), I/O contract.
 * - Validar script, deploy, testar com input de exemplo (mostra saída/erro do sandbox).
 * - Excluir com confirmação.
 * - Estados: loading (skeleton), vazio (EmptyState + CTA), erro (retry).
 */

interface ToolItem {
  id: string;
  name: string;
  description: string;
  language: string;
  script: string;
  inputs: unknown[];
  outputs: unknown[];
  status: string;
  created_at: string;
  updated_at: string;
  usageCount?: number;
}

interface TestResult {
  success: boolean;
  output?: string;
  error?: string;
  duration_ms?: number;
}

const LANGUAGE_OPTIONS = [
  { value: "python", label: "Python" },
  { value: "javascript", label: "JavaScript" },
];

const STATUS_LABELS: Record<string, string> = {
  draft: "Rascunho",
  deployed: "Deployed",
  error: "Erro",
};

interface ToolFormState {
  name: string;
  description: string;
  language: string;
  script: string;
  inputs: string;
  outputs: string;
}

const EMPTY_FORM: ToolFormState = {
  name: "",
  description: "",
  language: "python",
  script: "",
  inputs: "[]",
  outputs: "[]",
};

function parseJsonArray(raw: string, field: string): unknown[] {
  const trimmed = raw.trim();
  if (!trimmed) return [];
  const parsed = JSON.parse(trimmed);
  if (!Array.isArray(parsed)) {
    throw new Error(`${field} deve ser uma lista JSON`);
  }
  return parsed;
}

export function ToolsEditor() {
  const { addToast } = useToast();
  const [tools, setTools] = React.useState<ToolItem[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const [modalOpen, setModalOpen] = React.useState(false);
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [form, setForm] = React.useState<ToolFormState>(EMPTY_FORM);
  const [formError, setFormError] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);

  const [deleting, setDeleting] = React.useState<ToolItem | null>(null);
  const [deleteBusy, setDeleteBusy] = React.useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = React.useState(false);

  const [testing, setTesting] = React.useState<ToolItem | null>(null);
  const [testInput, setTestInput] = React.useState("");
  const [testResult, setTestResult] = React.useState<TestResult | null>(null);
  const [testBusy, setTestBusy] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.list<ToolItem>("/api/tools", { page: 1, limit: 100 });
      setTools(res.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao carregar tools");
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

  const openEdit = React.useCallback((tool: ToolItem) => {
    setEditingId(tool.id);
    setForm({
      name: tool.name,
      description: tool.description,
      language: tool.language,
      script: tool.script,
      inputs: JSON.stringify(tool.inputs ?? [], null, 2),
      outputs: JSON.stringify(tool.outputs ?? [], null, 2),
    });
    setFormError(null);
    setModalOpen(true);
  }, []);

  const handleSave = React.useCallback(async () => {
    setFormError(null);

    let inputs: unknown[];
    let outputs: unknown[];
    try {
      inputs = parseJsonArray(form.inputs, "Inputs");
      outputs = parseJsonArray(form.outputs, "Outputs");
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "JSON inválido");
      return;
    }

    if (!form.name.trim()) {
      setFormError("Nome é obrigatório");
      return;
    }
    if (!form.script.trim()) {
      setFormError("Script é obrigatório");
      return;
    }

    const body = {
      name: form.name.trim(),
      description: form.description.trim(),
      language: form.language,
      script: form.script,
      inputs,
      outputs,
    };

    setSaving(true);
    try {
      if (editingId) {
        await api.put(`/api/tools/${editingId}`, body);
        addToast("success", "Tool atualizada");
      } else {
        await api.post("/api/tools", body);
        addToast("success", "Tool criada");
      }
      setModalOpen(false);
      await load();
    } catch (e) {
      if (e instanceof ApiError && e.details?.errors) {
        setFormError(JSON.stringify(e.details.errors));
      } else {
        setFormError(e instanceof Error ? e.message : "Erro ao salvar tool");
      }
    } finally {
      setSaving(false);
    }
  }, [form, editingId, addToast, load]);

  const handleDelete = React.useCallback(async () => {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      await api.delete(`/api/tools/${deleting.id}`);
      addToast("info", "Tool excluída");
      setDeleting(null);
      setDeleteModalOpen(false);
      await load();
    } catch (e) {
      addToast("error", e instanceof Error ? e.message : "Erro ao excluir tool");
    } finally {
      setDeleteBusy(false);
    }
  }, [deleting, addToast, load]);

  const handleDeploy = React.useCallback(async (tool: ToolItem) => {
    try {
      await api.post(`/api/tools/${tool.id}/deploy`);
      addToast("success", "Tool deployada");
      await load();
    } catch (e) {
      addToast("error", e instanceof Error ? e.message : "Erro ao deployar tool");
    }
  }, [addToast, load]);

  const handleTest = React.useCallback(async () => {
    if (!testing) return;
    setTestBusy(true);
    setTestResult(null);
    try {
      const input = JSON.parse(testInput || "{}");
      // E8: o backend espera { args } (POST /api/tools/{id}/test); com
      // { input } o sandbox ignorava os argumentos (execute(**args)).
      const started = performance.now();
      const res = await api.post<{ result: Record<string, unknown> }>(
        `/api/tools/${testing.id}/test`,
        { args: input }
      );
      // O sandbox devolve { error, traceback } quando o script falha.
      const r = res.result ?? {};
      if (r.error !== undefined) {
        setTestResult({
          success: false,
          error: `${r.error}${r.traceback ? `\n${r.traceback}` : ""}`,
          duration_ms: Math.round(performance.now() - started),
        });
      } else {
        setTestResult({
          success: true,
          output: JSON.stringify(r, null, 2),
          duration_ms: Math.round(performance.now() - started),
        });
      }
    } catch (e) {
      // E7: erro do sandbox: o envelope traz a mensagem em details.output
      // ou details.error; "Erro" genérico escondia o diagnóstico real.
      const d = e instanceof ApiError ? e.details : undefined;
      const detailMsg =
        (d && (d.output ?? d.error ?? d.message)) as string | undefined;
      if (detailMsg && typeof detailMsg === "string") {
        setTestResult({ success: false, error: detailMsg });
      } else {
        setTestResult({
          success: false,
          error: e instanceof Error && e.message ? e.message : "Erro ao testar",
        });
      }
    } finally {
      setTestBusy(false);
    }
  }, [testing, testInput]);

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
  } else if (tools.length === 0) {
    content = (
      <EmptyState
        icon={Wrench}
        title="Nenhuma tool ainda"
        description="Tools custom são scripts Python/JS que os agentes podem executar."
        action={
          <Button variant="primary" onClick={openCreate}>
            <Plus size={14} aria-hidden="true" />
            Criar primeira tool
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
            Nova tool
          </Button>
        </div>

        <DataTable<ToolItem>
          columns={[
            { key: "name", header: "Nome", sortable: true },
            { key: "status", header: "Status", sortable: true, render: (t) => STATUS_LABELS[t.status] ?? t.status },
            { key: "description", header: "Descrição", render: (t) => t.description || "—" },
            { key: "usageCount", header: "Usos", sortable: true, render: (t) => `${t.usageCount ?? 0} agentes` },
          ]}
          rows={tools}
          rowKey={(t) => t.id}
          searchPlaceholder="Buscar tools…"
          onRowMenu={(tool, action) => {
            if (action === "edit") openEdit(tool);
            if (action === "test") {
              setTesting(tool);
              setTestInput("{}");
              setTestResult(null);
            }
            if (action === "deploy") void handleDeploy(tool);
            if (action === "delete") {
              setDeleting(tool);
              setDeleteModalOpen(true);
            }
          }}
          rowMenuItems={[
            { label: "Editar", action: "edit" },
            { label: "Testar", action: "test" },
            { label: "Deploy", action: "deploy" },
            { label: "Excluir", action: "delete", danger: true },
          ]}
          emptyMessage="Nenhuma tool encontrada"
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
        title={editingId ? "Editar tool" : "Nova tool"}
        footer={
          <>
            <Button size="sm" onClick={() => setModalOpen(false)} disabled={saving}>
              Cancelar
            </Button>
            <Button size="sm" variant="primary" onClick={() => void handleSave()} loading={saving}>
              {editingId ? "Salvar alterações" : "Criar tool"}
            </Button>
          </>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          <Input
            id="tool-name"
            label="Nome"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            placeholder="Ex.: Calcular hash"
            disabled={saving}
          />
          <Input
            id="tool-description"
            label="Descrição"
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            placeholder="O que esta tool faz"
            disabled={saving}
          />
          <Select
            id="tool-language"
            label="Linguagem"
            value={form.language}
            options={LANGUAGE_OPTIONS}
            onChange={(e) => setForm((f) => ({ ...f, language: e.target.value }))}
            disabled={saving}
          />
          <Textarea
            id="tool-script"
            label="Script"
            value={form.script}
            onChange={(e) => setForm((f) => ({ ...f, script: e.target.value }))}
            rows={12}
              // E7: o sandbox chama `execute(**args)` (app/tools/sandbox.py);
              // o placeholder antigo (def main(inputs)) era a convenção errada
              // e qualquer tool criada com ele falhava no teste.
              placeholder={
                form.language === "python"
                  ? "def execute(**kwargs):\n    # kwargs = inputs da tool (nomes do JSON de inputs)\n    return {'result': ...}"
                  : "function main(inputs) {\n  return { result: ... };\n}"
              }
            disabled={saving}
            style={{ fontFamily: "var(--font-mono)", fontSize: "12px" }}
          />
          <Textarea
            id="tool-inputs"
            label="Inputs (JSON)"
            value={form.inputs}
            onChange={(e) => setForm((f) => ({ ...f, inputs: e.target.value }))}
            rows={3}
            placeholder='[{"name": "data", "type": "string", "required": true}]'
            disabled={saving}
            style={{ fontFamily: "var(--font-mono)", fontSize: "12px" }}
          />
          <Textarea
            id="tool-outputs"
            label="Outputs (JSON)"
            value={form.outputs}
            onChange={(e) => setForm((f) => ({ ...f, outputs: e.target.value }))}
            rows={3}
            placeholder='[{"name": "result", "type": "string", "required": false}]'
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

      {/* Modal testar */}
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
              Executar teste
            </Button>
          </>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          <Textarea
            id="tool-test-input"
            label="Input de exemplo (JSON)"
            value={testInput}
            onChange={(e) => setTestInput(e.target.value)}
            rows={4}
            placeholder='{"data": "exemplo"}'
            disabled={testBusy}
            style={{ fontFamily: "var(--font-mono)", fontSize: "12px" }}
          />
          {testResult && (
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
                  {testResult.success ? "Sucesso" : "Erro"}
                </span>
                {testResult.duration_ms && (
                  <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                    ({testResult.duration_ms}ms)
                  </span>
                )}
              </div>
              <pre
                style={{
                  fontSize: "12px",
                  fontFamily: "var(--font-mono)",
                  margin: 0,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                }}
              >
                {testResult.output ?? testResult.error}
              </pre>
            </div>
          )}
        </div>
      </Modal>

      {/* Modal confirmar exclusão */}
      <Modal
        open={deleteModalOpen}
        onClose={() => setDeleteModalOpen(false)}
        title="Excluir tool"
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
          Excluir a tool <strong>{deleting?.name}</strong>? Agentes que a referenciam
          precisarão ser atualizados.
        </p>
      </Modal>
    </div>
  );
}
