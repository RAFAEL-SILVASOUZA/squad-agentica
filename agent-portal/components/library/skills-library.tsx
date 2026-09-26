"use client";

import * as React from "react";
import {
  BookOpen,
  Plus,
  Pencil,
  Trash2,
  RefreshCw,
  AlertTriangle,
  Eye,
  Code2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import { Tabs } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api";
import { MarkdownPreview } from "./markdown-preview";

/**
 * SkillsLibrary (fe-library, protótipo view-SKILLS).
 * - Grid de skills do usuário (GET /api/skills).
 * - Criar/editar via modal: nome, descrição, categoria, template markdown
 *   (editor com preview), variáveis, inputs/outputs (JSON), integrações.
 * - Excluir com confirmação.
 * - Estados: loading (skeleton), vazio (EmptyState + CTA), erro (retry).
 *
 * O backend retorna snake_case (created_at/updated_at/required_integrations);
 * a extensão local abaixo espelha o contrato real do router (be-skills).
 */

interface SkillItem {
  id: string;
  name: string;
  description: string;
  category: string;
  type: string;
  definition: { template: string; variables: string[] };
  inputs: unknown[];
  outputs: unknown[];
  required_integrations: string[];
  created_at: string;
  updated_at: string;
}

const CATEGORY_OPTIONS = [
  { value: "code", label: "Código" },
  { value: "docs", label: "Documentação" },
  { value: "infra", label: "Infraestrutura" },
  { value: "communication", label: "Comunicação" },
  { value: "analysis", label: "Análise" },
];

const CATEGORY_LABELS: Record<string, string> = {
  code: "Código",
  docs: "Documentação",
  infra: "Infraestrutura",
  communication: "Comunicação",
  analysis: "Análise",
};

interface SkillFormState {
  name: string;
  description: string;
  category: string;
  template: string;
  variables: string;
  inputs: string;
  outputs: string;
  requiredIntegrations: string;
}

const EMPTY_FORM: SkillFormState = {
  name: "",
  description: "",
  category: "code",
  template: "",
  variables: "",
  inputs: "[]",
  outputs: "[]",
  requiredIntegrations: "",
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

export function SkillsLibrary() {
  const { addToast } = useToast();
  const [skills, setSkills] = React.useState<SkillItem[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const [modalOpen, setModalOpen] = React.useState(false);
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [form, setForm] = React.useState<SkillFormState>(EMPTY_FORM);
  const [formError, setFormError] = React.useState<string | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [previewTab, setPreviewTab] = React.useState("edit");

  const [deleting, setDeleting] = React.useState<SkillItem | null>(null);
  const [deleteBusy, setDeleteBusy] = React.useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.list<SkillItem>("/api/skills", { page: 1, limit: 100 });
      setSkills(res.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao carregar skills");
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
    setPreviewTab("edit");
    setModalOpen(true);
  }, []);

  const openEdit = React.useCallback((skill: SkillItem) => {
    setEditingId(skill.id);
    setForm({
      name: skill.name,
      description: skill.description,
      category: skill.category,
      template: skill.definition?.template ?? "",
      variables: (skill.definition?.variables ?? []).join(", "),
      inputs: JSON.stringify(skill.inputs ?? [], null, 2),
      outputs: JSON.stringify(skill.outputs ?? [], null, 2),
      requiredIntegrations: (skill.required_integrations ?? []).join(", "),
    });
    setFormError(null);
    setPreviewTab("edit");
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
    if (!form.template.trim()) {
      setFormError("Template é obrigatório");
      return;
    }

    const body = {
      name: form.name.trim(),
      description: form.description.trim(),
      category: form.category,
      definition: {
        template: form.template,
        variables: form.variables
          .split(",")
          .map((v) => v.trim())
          .filter(Boolean),
      },
      inputs,
      outputs,
      required_integrations: form.requiredIntegrations
        .split(",")
        .map((v) => v.trim())
        .filter(Boolean),
    };

    setSaving(true);
    try {
      if (editingId) {
        await api.put(`/api/skills/${editingId}`, body);
        addToast("success", "Skill atualizada");
      } else {
        await api.post("/api/skills", body);
        addToast("success", "Skill criada");
      }
      setModalOpen(false);
      await load();
    } catch (e) {
      if (e instanceof ApiError && e.details?.errors) {
        setFormError(JSON.stringify(e.details.errors));
      } else {
        setFormError(e instanceof Error ? e.message : "Erro ao salvar skill");
      }
    } finally {
      setSaving(false);
    }
  }, [form, editingId, addToast, load]);

  const handleDelete = React.useCallback(async () => {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      await api.delete(`/api/skills/${deleting.id}`);
      addToast("info", "Skill excluída");
      setDeleting(null);
      setDeleteModalOpen(false);
      await load();
    } catch (e) {
      addToast("error", e instanceof Error ? e.message : "Erro ao excluir skill");
    } finally {
      setDeleteBusy(false);
    }
  }, [deleting, addToast, load]);

  // ─── Content ──────────────────────────────────────────────────────────────
  let content: React.ReactNode;

  if (loading) {
    content = (
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
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
  } else if (skills.length === 0) {
    content = (
      <EmptyState
        icon={BookOpen}
        title="Nenhum skill ainda"
        description="Skills são blocos reutilizáveis de prompt que os agentes podem usar."
        action={
          <Button variant="primary" onClick={openCreate}>
            <Plus size={14} aria-hidden="true" />
            Criar primeiro skill
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
            Nova skill
          </Button>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
            gap: "12px",
          }}
        >
          {skills.map((skill) => (
            <Card key={skill.id} hoverable onClick={() => openEdit(skill)}>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: "8px",
                }}
              >
                <span
                  style={{
                    fontSize: "13px",
                    fontWeight: 600,
                    color: "var(--text)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {skill.name}
                </span>
                <Badge status="neutral" label={CATEGORY_LABELS[skill.category] ?? skill.category} />
              </div>
              <p
                style={{
                  fontSize: "12px",
                  color: "var(--text-secondary)",
                  margin: "8px 0 0",
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                }}
              >
                {skill.description || "Sem descrição"}
              </p>
              <div
                style={{
                  display: "flex",
                  gap: "8px",
                  marginTop: "12px",
                  paddingTop: "10px",
                  borderTop: "1px solid var(--border-subtle)",
                }}
              >
                <Button
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    openEdit(skill);
                  }}
                  aria-label={`Editar skill ${skill.name}`}
                >
                  <Pencil size={12} aria-hidden="true" />
                  Editar
                </Button>
                <Button
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    setDeleting(skill);
                    setDeleteModalOpen(true);
                  }}
                  aria-label={`Excluir skill ${skill.name}`}
                >
                  <Trash2 size={12} aria-hidden="true" />
                  Excluir
                </Button>
              </div>
            </Card>
          ))}
        </div>
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
        title={editingId ? "Editar skill" : "Nova skill"}
        footer={
          <>
            <Button size="sm" onClick={() => setModalOpen(false)} disabled={saving}>
              Cancelar
            </Button>
            <Button size="sm" variant="primary" onClick={() => void handleSave()} loading={saving}>
              {editingId ? "Salvar alterações" : "Criar skill"}
            </Button>
          </>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          <Input
            id="skill-name"
            label="Nome"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            placeholder="Ex.: Revisar código"
            disabled={saving}
          />
          <Input
            id="skill-description"
            label="Descrição"
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            placeholder="O que esta skill faz"
            disabled={saving}
          />
          <Select
            id="skill-category"
            label="Categoria"
            value={form.category}
            options={CATEGORY_OPTIONS}
            onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
            disabled={saving}
          />

          <div>
            <Tabs
              tabs={[
                { id: "edit", label: "Editar" },
                { id: "preview", label: "Pré-visualizar" },
              ]}
              activeTab={previewTab}
              onTabChange={setPreviewTab}
            />
            <div style={{ paddingTop: "12px" }}>
              {previewTab === "edit" ? (
                <Textarea
                  id="skill-template"
                  label="Template (markdown)"
                  value={form.template}
                  onChange={(e) => setForm((f) => ({ ...f, template: e.target.value }))}
                  rows={10}
                  placeholder={"## Instruções\n\nEscreva o prompt da skill usando {{variáveis}}."}
                  disabled={saving}
                  style={{ fontFamily: "var(--font-mono)", fontSize: "12px" }}
                />
              ) : (
                <div
                  style={{
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-sm)",
                    padding: "12px",
                    minHeight: 120,
                    background: "var(--bg-elevated)",
                  }}
                >
                  <MarkdownPreview source={form.template} />
                </div>
              )}
            </div>
          </div>

          <Input
            id="skill-variables"
            label="Variáveis"
            value={form.variables}
            onChange={(e) => setForm((f) => ({ ...f, variables: e.target.value }))}
            placeholder="Separadas por vírgula: contexto, objetivo"
            hint="Variáveis referenciadas no template como {{nome}}."
            disabled={saving}
          />
          <Textarea
            id="skill-inputs"
            label="Inputs (JSON)"
            value={form.inputs}
            onChange={(e) => setForm((f) => ({ ...f, inputs: e.target.value }))}
            rows={3}
            placeholder='[{"name": "arquivo", "type": "string", "required": true}]'
            disabled={saving}
            style={{ fontFamily: "var(--font-mono)", fontSize: "12px" }}
          />
          <Textarea
            id="skill-outputs"
            label="Outputs (JSON)"
            value={form.outputs}
            onChange={(e) => setForm((f) => ({ ...f, outputs: e.target.value }))}
            rows={3}
            placeholder='[{"name": "resultado", "type": "string", "required": false}]'
            disabled={saving}
            style={{ fontFamily: "var(--font-mono)", fontSize: "12px" }}
          />
          <Input
            id="skill-integrations"
            label="Integrações requeridas"
            value={form.requiredIntegrations}
            onChange={(e) => setForm((f) => ({ ...f, requiredIntegrations: e.target.value }))}
            placeholder="Separadas por vírgula: github, azure"
            disabled={saving}
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

      {/* Modal confirmar exclusão */}
      <Modal
        open={deleteModalOpen}
        onClose={() => setDeleteModalOpen(false)}
        title="Excluir skill"
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
          Excluir a skill <strong>{deleting?.name}</strong>? Agentes que a referenciam
          precisarão ser atualizados.
        </p>
      </Modal>
    </div>
  );
}
