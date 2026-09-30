"use client";

import * as React from "react";
import { FileText, Plus, RefreshCw, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api";
import { KbHeader } from "@/components/knowledge/kb-header";
import { DocumentsPanel } from "@/components/knowledge/documents-panel";
import { KbChat } from "@/components/knowledge/kb-chat";
import type { KnowledgeBaseItem } from "@/components/knowledge/types";

/**
 * KnowledgeView (fe-library, protótipo view-KNOWLEDGE).
 * - Sidebar de bases de conhecimento (GET /api/knowledge).
 * - Criar base com escopo (POST /api/knowledge).
 * - Painel da base composto por KbHeader (editar/excluir), DocumentsPanel
 *   (upload/remover/duplicados) e KbChat (conversas com fontes).
 * - Estados: loading (skeleton), vazio (EmptyState + CTA), erro (retry).
 */

const SCOPE_OPTIONS = [
  { value: "global", label: "Global" },
  { value: "agent", label: "Agente" },
  { value: "pipeline", label: "Pipeline" },
];

// source é OBRIGATÓRIO no POST /api/knowledge (spec 9.3); upload é a fonte
// padrão da V1 (E6: o form não enviava source e o backend respondia 422).
const SOURCE_OPTIONS = [
  { value: "upload", label: "Upload de arquivo" },
  { value: "url", label: "URL" },
  { value: "vector-db", label: "Vector DB" },
];

// E15: grid fixo "240px 1fr" estourava a largura em telas estreitas (390px).
// Sidebar de 240px ao lado do painel; abaixo de ~580px os dois empilham.
const LAYOUT: React.CSSProperties = { display: "flex", flexWrap: "wrap", gap: "16px" };
const SIDEBAR: React.CSSProperties = { flex: "1 1 240px", minWidth: 0 };
const MAIN: React.CSSProperties = { flex: "999 1 320px", minWidth: 0 };


const EMPTY_CREATE_FORM = {
  name: "",
  description: "",
  scope: "global",
  source: "upload",
  similarityThreshold: "0.7",
  topK: "5",
};

export function KnowledgeView() {
  const { addToast } = useToast();
  const [bases, setBases] = React.useState<KnowledgeBaseItem[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const [selectedBase, setSelectedBase] = React.useState<KnowledgeBaseItem | null>(null);

  const [createModalOpen, setCreateModalOpen] = React.useState(false);
  const [createForm, setCreateForm] = React.useState(EMPTY_CREATE_FORM);
  const [createFormError, setCreateFormError] = React.useState<string | null>(null);
  const [createBusy, setCreateBusy] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.list<KnowledgeBaseItem>("/api/knowledge", { page: 1, limit: 100 });
      setBases(res.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Falha ao carregar bases de conhecimento");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const handleCreate = React.useCallback(async () => {
    setCreateFormError(null);
    if (!createForm.name.trim()) {
      setCreateFormError("Nome é obrigatório");
      return;
    }

    setCreateBusy(true);
    try {
      const threshold = Number(createForm.similarityThreshold.replace(",", "."));
      const topK = Number(createForm.topK);
      if (!(threshold >= 0 && threshold <= 1) || !Number.isInteger(topK) || topK < 1) {
        setCreateFormError("Limiar deve estar entre 0 e 1 e Top K ser um inteiro maior que 0.");
        setCreateBusy(false);
        return;
      }
      await api.post("/api/knowledge", {
        name: createForm.name.trim(),
        description: createForm.description.trim(),
        scope: createForm.scope,
        source: createForm.source,
        similarityThreshold: threshold,
        topK,
      });
      addToast("success", "Base de conhecimento criada");
      setCreateModalOpen(false);
      setCreateForm(EMPTY_CREATE_FORM);
      await load();
    } catch (e) {
      // E6: não expor o JSON cru do pydantic — mostra uma mensagem amigável.
      const errors = e instanceof ApiError ? e.details?.errors : undefined;
      setCreateFormError(Array.isArray(errors) && errors.every((item) => typeof item === "string")
        ? errors.join("; ")
        : e instanceof Error ? e.message : "Erro ao criar base");
    } finally {
      setCreateBusy(false);
    }
  }, [createForm, addToast, load]);

  const updateBase = React.useCallback((next: KnowledgeBaseItem) => {
    setBases((prev) => prev.map((b) => (b.id === next.id ? { ...b, ...next } : b)));
    setSelectedBase((prev) => (prev && prev.id === next.id ? { ...prev, ...next } : prev));
  }, []);

  // ─── Content ──────────────────────────────────────────────────────────────
  let content: React.ReactNode;

  if (loading) {
    content = (
      <div style={LAYOUT}>
        <div style={{ ...SIDEBAR, display: "flex", flexDirection: "column", gap: "8px" }}>
          {[0, 1, 2].map((i) => (
            <Card key={i}>
              <Skeleton width="80%" height={14} />
            </Card>
          ))}
        </div>
        <div style={MAIN}>
          <Skeleton width="100%" height={200} />
        </div>
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
  } else {
    content = (
      <div style={LAYOUT}>
        {/* Sidebar de bases */}
        <div style={{ ...SIDEBAR, display: "flex", flexDirection: "column", gap: "8px" }}>
          <Button variant="primary" size="sm" onClick={() => setCreateModalOpen(true)}>
            <Plus size={14} aria-hidden="true" />
            Nova base
          </Button>

          {bases.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="Nenhuma base ainda"
              description="Crie uma base de conhecimento para armazenar documentos."
            />
          ) : (
            bases.map((base) => (
              <Card
                key={base.id}
                hoverable
                onClick={() => setSelectedBase(base)}
                style={{
                  border: selectedBase?.id === base.id ? "2px solid var(--accent)" : undefined,
                }}
              >
                <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
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
                    {base.name}
                  </span>
                  <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                    {base.documentCount} documentos
                  </span>
                </div>
              </Card>
            ))
          )}
        </div>

        {/* Painel principal */}
        <div style={{ ...MAIN, display: "flex", flexDirection: "column", gap: "16px" }}>
          {!selectedBase ? (
            <EmptyState
              icon={FileText}
              title="Selecione uma base"
              description="Escolha uma base de conhecimento na sidebar para ver os documentos."
            />
          ) : (
            <React.Fragment key={selectedBase.id}>
              <KbHeader
                base={selectedBase}
                onUpdated={updateBase}
                onDeleted={() => {
                  setSelectedBase(null);
                  void load();
                }}
              />
              <DocumentsPanel
                baseId={selectedBase.id}
                onCountChange={(count) => updateBase({ ...selectedBase, documentCount: count })}
              />
              <KbChat baseId={selectedBase.id} />
            </React.Fragment>
          )}
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Breadcrumb: “Knowledge / <base>” quando há base selecionada. */}
      <Breadcrumb
        items={
          selectedBase
            ? [{ label: "Knowledge" }, { label: selectedBase.name }]
            : [{ label: "Knowledge" }]
        }
      />

      {content}

      {/* Modal criar base */}
      <Modal
        open={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        title="Nova base de conhecimento"
        footer={
          <>
            <Button size="sm" onClick={() => setCreateModalOpen(false)} disabled={createBusy}>
              Cancelar
            </Button>
            <Button size="sm" variant="primary" onClick={() => void handleCreate()} loading={createBusy}>
              Criar base
            </Button>
          </>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          <Input
            id="kb-name"
            label="Nome"
            value={createForm.name}
            onChange={(e) => setCreateForm((f) => ({ ...f, name: e.target.value }))}
            placeholder="Ex.: Base de documentação"
            disabled={createBusy}
          />
          <Input
            id="kb-description"
            label="Descrição"
            value={createForm.description}
            onChange={(e) => setCreateForm((f) => ({ ...f, description: e.target.value }))}
            placeholder="O que esta base contém"
            disabled={createBusy}
          />
          <Select
            id="kb-scope"
            label="Escopo"
            value={createForm.scope}
            options={SCOPE_OPTIONS}
            onChange={(e) => setCreateForm((f) => ({ ...f, scope: e.target.value }))}
            disabled={createBusy}
          />
          <Select
            id="kb-source"
            label="Fonte"
            value={createForm.source}
            options={SOURCE_OPTIONS}
            onChange={(e) => setCreateForm((f) => ({ ...f, source: e.target.value }))}
            disabled={createBusy}
          />
          {/* Spec §7: topK e similarityThreshold são configuráveis por base. O
              limiar certo depende do modelo de embeddings (0,7 corta trechos
              relevantes com modelos locais). */}
          <div style={{ display: "flex", gap: "12px" }}>
            <Input
              id="kb-threshold"
              label="Limiar de similaridade (0–1)"
              inputMode="decimal"
              value={createForm.similarityThreshold}
              onChange={(e) => setCreateForm((f) => ({ ...f, similarityThreshold: e.target.value }))}
              disabled={createBusy}
            />
            <Input
              id="kb-topk"
              label="Top K"
              inputMode="numeric"
              value={createForm.topK}
              onChange={(e) => setCreateForm((f) => ({ ...f, topK: e.target.value }))}
              disabled={createBusy}
            />
          </div>
          {createFormError && (
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
              {createFormError}
            </p>
          )}
        </div>
      </Modal>
    </div>
  );
}
