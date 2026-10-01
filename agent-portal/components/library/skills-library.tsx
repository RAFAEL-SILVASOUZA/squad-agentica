"use client";

import * as React from "react";
import {
  BookOpen,
  Plus,
  Trash2,
  RefreshCw,
  AlertTriangle,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { Modal } from "@/components/ui/modal";
import { Tabs } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { DataTable } from "@/components/ui/data-table";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api";
import { MarkdownPreview } from "./markdown-preview";
import { PortsEditor, type Port } from "@/components/ports/ports-editor";

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
  inputs: Port[];
  outputs: Port[];
  required_integrations: string[];
  created_at: string;
  updated_at: string;
  usageCount?: number;
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

// Tipos de port (mesma whitelist do contrato de agente, spec 4.1).
const PORT_TYPE_OPTIONS = ["document", "code", "artifact", "signal"];

interface SkillFormState {
  name: string;
  description: string;
  category: string;
  template: string;
  variables: string;
  inputs: Port[];
  outputs: Port[];
  requiredIntegrations: string;
}

const EMPTY_FORM: SkillFormState = {
  name: "",
  description: "",
  category: "code",
  template: "",
  variables: "",
  inputs: [],
  outputs: [],
  requiredIntegrations: "",
};

// Contrato do endpoint POST /api/skills/generate (geração interativa por IA).
interface GenQuestion {
  text: string;
  options: string[];
}

interface GenSkill {
  name: string;
  description: string;
  category: string;
  template: string;
  variables: string[];
  inputs: Port[];
  outputs: Port[];
  required_integrations: string[];
}

interface GenResponse {
  status: "questions" | "done";
  question: GenQuestion | null;
  skill: GenSkill | null;
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

  // Geração de skill por IA (interativa): botão "AI" → mini-modais de pergunta.
  const [genBusy, setGenBusy] = React.useState(false);
  const [genQuestion, setGenQuestion] = React.useState<GenQuestion | null>(null);
  const [genAnswers, setGenAnswers] = React.useState<{ question: string; answer: string }[]>([]);
  const [genAnswer, setGenAnswer] = React.useState("");

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
      inputs: skill.inputs ?? [],
      outputs: skill.outputs ?? [],
      requiredIntegrations: (skill.required_integrations ?? []).join(", "),
    });
    setFormError(null);
    setPreviewTab("edit");
    setModalOpen(true);
  }, []);

  const handleSave = React.useCallback(async () => {
    setFormError(null);

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
      inputs: form.inputs,
      outputs: form.outputs,
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

  const applyGenerateResponse = React.useCallback(
    (res: GenResponse) => {
      if (res.status === "questions" && res.question) {
        setGenQuestion(res.question);
        setGenAnswer("");
      } else if (res.status === "done" && res.skill) {
        const s = res.skill;
        setForm((f) => ({
          ...f,
          name: s.name,
          description: s.description || f.description,
          category: s.category,
          template: s.template,
          variables: (s.variables ?? []).join(", "),
          inputs: s.inputs ?? [],
          outputs: s.outputs ?? [],
          requiredIntegrations: (s.required_integrations ?? []).join(", "),
        }));
        setGenQuestion(null);
        setGenAnswers([]);
        setPreviewTab("edit");
        addToast("success", "Skill gerada pela IA. Revise antes de salvar.");
      }
    },
    [addToast]
  );

  const startGenerate = React.useCallback(async () => {
    setGenAnswers([]);
    setGenAnswer("");
    setGenBusy(true);
    try {
      const res = await api.post<GenResponse>("/api/skills/generate", {
        description: form.description.trim(),
        answers: [],
      });
      applyGenerateResponse(res);
    } catch (e) {
      addToast("error", e instanceof Error ? e.message : "Falha ao gerar skill com IA");
    } finally {
      setGenBusy(false);
    }
  }, [form.description, applyGenerateResponse, addToast]);

  const answerQuestion = React.useCallback(
    async (answer: string) => {
      if (!genQuestion) return;
      const nextAnswers = [...genAnswers, { question: genQuestion.text, answer }];
      setGenAnswers(nextAnswers);
      setGenAnswer("");
      setGenBusy(true);
      try {
        const res = await api.post<GenResponse>("/api/skills/generate", {
          description: form.description.trim(),
          answers: nextAnswers,
        });
        applyGenerateResponse(res);
      } catch (e) {
        addToast("error", e instanceof Error ? e.message : "Falha ao gerar skill com IA");
      } finally {
        setGenBusy(false);
      }
    },
    [genQuestion, genAnswers, form.description, applyGenerateResponse, addToast]
  );

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

        <DataTable<SkillItem>
          columns={[
            { key: "name", header: "Nome", sortable: true },
            { key: "category", header: "Categoria", sortable: true, render: (s) => CATEGORY_LABELS[s.category] ?? s.category },
            { key: "description", header: "Descrição", render: (s) => s.description || "—" },
            { key: "usageCount", header: "Usos", sortable: true, render: (s) => `${s.usageCount ?? 0} agentes` },
          ]}
          rows={skills}
          rowKey={(s) => s.id}
          searchPlaceholder="Buscar skills…"
          filters={[
            {
              key: "category",
              label: "Categoria",
              options: CATEGORY_OPTIONS,
            },
          ]}
          onRowMenu={(skill, action) => {
            if (action === "edit") openEdit(skill);
            if (action === "delete") {
              setDeleting(skill);
              setDeleteModalOpen(true);
            }
          }}
          rowMenuItems={[
            { label: "Editar", action: "edit" },
            { label: "Excluir", action: "delete", danger: true },
          ]}
          emptyMessage="Nenhuma skill encontrada"
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
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "8px",
              }}
            >
              <label
                htmlFor="skill-template"
                style={{ fontSize: "13px", fontWeight: 500, color: "var(--text)" }}
              >
                Template (markdown)
              </label>
              <Button
                size="sm"
                onClick={() => void startGenerate()}
                loading={genBusy}
                disabled={saving}
                title="Gera a skill inteira a partir da descrição"
              >
                <Sparkles size={13} aria-hidden="true" />
                Gerar com IA
              </Button>
            </div>
            <div style={{ paddingTop: "8px" }}>
              <Tabs
                tabs={[
                  { id: "edit", label: "Editar" },
                  { id: "preview", label: "Pré-visualizar" },
                ]}
                activeTab={previewTab}
                onTabChange={setPreviewTab}
              />
            </div>
            <div style={{ paddingTop: "12px" }}>
              {previewTab === "edit" ? (
                <Textarea
                  id="skill-template"
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
          <PortsEditor
            label="Inputs"
            value={form.inputs}
            onChange={(ports) => setForm((f) => ({ ...f, inputs: ports }))}
            types={PORT_TYPE_OPTIONS}
          />
          <PortsEditor
            label="Outputs"
            value={form.outputs}
            onChange={(ports) => setForm((f) => ({ ...f, outputs: ports }))}
            types={PORT_TYPE_OPTIONS}
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

      {/* Mini-modal de pergunta da IA (empilha sobre o modal de criação) */}
      <Modal
        open={genQuestion !== null}
        onClose={() => setGenQuestion(null)}
        title="A IA tem uma pergunta"
        size="sm"
        busy={genBusy}
        footer={
          <>
            <Button size="sm" onClick={() => setGenQuestion(null)} disabled={genBusy}>
              Cancelar
            </Button>
            <Button
              size="sm"
              variant="primary"
              onClick={() => void answerQuestion(genAnswer.trim())}
              loading={genBusy}
              disabled={!genAnswer.trim()}
            >
              Responder
            </Button>
          </>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          <p style={{ fontSize: "13px", color: "var(--text)", margin: 0 }}>
            {genQuestion?.text}
          </p>
          {genQuestion && genQuestion.options.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              {genQuestion.options.map((opt) => (
                <button
                  key={opt}
                  type="button"
                  onClick={() => setGenAnswer(opt)}
                  disabled={genBusy}
                  style={{
                    textAlign: "left",
                    padding: "8px 12px",
                    borderRadius: "var(--radius-sm)",
                    border: `1px solid ${genAnswer === opt ? "var(--accent)" : "var(--border)"}`,
                    background: genAnswer === opt ? "var(--accent-subtle)" : "var(--bg-elevated)",
                    color: "var(--text)",
                    fontSize: "13px",
                    cursor: genBusy ? "default" : "pointer",
                    transition: "border-color var(--transition), background var(--transition)",
                  }}
                >
                  {opt}
                </button>
              ))}
            </div>
          )}
          <Input
            id="gen-answer"
            label={genQuestion && genQuestion.options.length > 0 ? "Ou escreva sua resposta" : "Sua resposta"}
            value={genAnswer}
            onChange={(e) => setGenAnswer(e.target.value)}
            placeholder="Digite aqui…"
            disabled={genBusy}
          />
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
