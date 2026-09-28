"use client";

import * as React from "react";
import {
  FileText,
  Plus,
  Trash2,
  RefreshCw,
  AlertTriangle,
  Upload,
  Search,
  CheckCircle2,
  XCircle,
  Clock,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api";

/**
 * KnowledgeView (fe-library, protótipo view-KNOWLEDGE).
 * - Sidebar de bases de conhecimento (GET /api/knowledge).
 * - Criar base com escopo (POST /api/knowledge).
 * - Upload de documentos com progresso e status de ingestão (POST /api/knowledge/{id}/upload).
 * - Consulta de teste com resultados e score (POST /api/knowledge/query).
 * - Rivvn visível mas desabilitado com a mensagem definida no contrato.
 * - Excluir base com confirmação.
 * - Estados: loading (skeleton), vazio (EmptyState + CTA), erro (retry).
 */

interface KnowledgeBaseItem {
  id: string;
  name: string;
  description: string | null;
  scope: string;
  source: string;
  documentCount: number;
  createdAt: string;
  updatedAt: string;
}

interface KnowledgeDocument {
  id: string;
  name: string;
  status: string;
  size: number;
  chunkCount: number;
  createdAt: string;
}

interface QueryResult {
  content: string;
  score: number;
  source: string;
}

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

const DOC_STATUS_LABELS: Record<string, string> = {
  processing: "Processando",
  ready: "Pronto",
  failed: "Falhou",
};


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
  const [documents, setDocuments] = React.useState<KnowledgeDocument[]>([]);
  const [docsLoading, setDocsLoading] = React.useState(false);

  const [createModalOpen, setCreateModalOpen] = React.useState(false);
  const [createForm, setCreateForm] = React.useState(EMPTY_CREATE_FORM);
  const [createFormError, setCreateFormError] = React.useState<string | null>(null);
  const [createBusy, setCreateBusy] = React.useState(false);

  const [deleting, setDeleting] = React.useState<KnowledgeBaseItem | null>(null);
  const [deleteBusy, setDeleteBusy] = React.useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = React.useState(false);

  const [uploading, setUploading] = React.useState(false);
  const [uploadProgress, setUploadProgress] = React.useState(0);

  const [query, setQuery] = React.useState("");
  const [queryResults, setQueryResults] = React.useState<QueryResult[]>([]);
  // Distingue "ainda não buscou" de "buscou e não achou" (estado vazio).
  const [queryDone, setQueryDone] = React.useState(false);
  const [queryBusy, setQueryBusy] = React.useState(false);
  const [queryError, setQueryError] = React.useState<string | null>(null);

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

  const loadDocuments = React.useCallback(async (baseId: string) => {
    setDocsLoading(true);
    try {
      // GET /api/knowledge/{id}/documents é PAGINADO (contrato §8): a lista
      // vem em ``res.items``, não como array direto (E9: documents.map is not
      // a function ao tratar a resposta como array).
      const res = await api.list<KnowledgeDocument>(`/api/knowledge/${baseId}/documents`, {
        page: 1,
        limit: 100,
      });
      setDocuments(res.items);
    } catch (e) {
      addToast("error", e instanceof Error ? e.message : "Erro ao carregar documentos");
    } finally {
      setDocsLoading(false);
    }
  }, [addToast]);

  React.useEffect(() => {
    void load();
  }, [load]);

  React.useEffect(() => {
    if (selectedBase) {
      void loadDocuments(selectedBase.id);
    } else {
      setDocuments([]);
    }
  }, [selectedBase, loadDocuments]);

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

  const handleDelete = React.useCallback(async () => {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      await api.delete(`/api/knowledge/${deleting.id}`);
      addToast("info", "Base de conhecimento excluída");
      if (selectedBase?.id === deleting.id) {
        setSelectedBase(null);
      }
      setDeleting(null);
      setDeleteModalOpen(false);
      await load();
    } catch (e) {
      addToast("error", e instanceof Error ? e.message : "Erro ao excluir base");
    } finally {
      setDeleteBusy(false);
    }
  }, [deleting, selectedBase, addToast, load]);

  const handleUpload = React.useCallback(async (file: File) => {
    if (!selectedBase) return;
    setUploading(true);
    setUploadProgress(0);

    const formData = new FormData();
    formData.append("file", file);

    // Simula progresso (o backend não suporta upload com progresso via fetch)
    const interval = setInterval(() => {
      setUploadProgress((p) => Math.min(p + 10, 90));
    }, 200);
    try {

      // E10: NUNCA fixar Content-Type manualmente em FormData — o browser
      // precisa inserir o próprio boundary em ``multipart/form-data``. Fixar
      // o header sem boundary gerava 400 no parse multipart do backend.
      await api.post(`/api/knowledge/${selectedBase.id}/upload`, formData);

      setUploadProgress(100);
      addToast("success", "Documento enviado para ingestão");
      // O contador da sidebar vem da listagem de bases; sem isto ficava em
      // "0 documentos" até recarregar a página.
      setBases((prev) =>
        prev.map((b) =>
          b.id === selectedBase.id ? { ...b, documentCount: b.documentCount + 1 } : b
        )
      );
      await loadDocuments(selectedBase.id);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Erro ao enviar documento";
      addToast("error", msg || "Erro ao enviar documento");
    } finally {
      clearInterval(interval);
      setUploading(false);
      setUploadProgress(0);
    }
  }, [selectedBase, addToast, loadDocuments]);

  const handleQuery = React.useCallback(async () => {
    if (!selectedBase || !query.trim()) return;
    setQueryBusy(true);
    setQueryError(null);
    setQueryResults([]);
    setQueryDone(false);

    try {
      const res = await api.post<{ chunks: QueryResult[] }>("/api/knowledge/query", {
        knowledgeBaseIds: [selectedBase.id],
        query: query.trim(),
      });
      setQueryResults(res.chunks);
      setQueryDone(true);
    } catch (e) {
      setQueryError(e instanceof Error ? e.message : "Erro na consulta");
    } finally {
      setQueryBusy(false);
    }
  }, [selectedBase, query]);

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
            <>
              {/* Header da base */}
              <Card>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <h2 style={{ fontSize: "16px", fontWeight: 700, color: "var(--text)", margin: 0 }}>
                      {selectedBase.name}
                    </h2>
                    <p style={{ fontSize: "12px", color: "var(--text-secondary)", margin: "4px 0 0" }}>
                      {selectedBase.description || "Sem descrição"}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    onClick={() => {
                      setDeleting(selectedBase);
                      setDeleteModalOpen(true);
                    }}
                    style={{ background: "var(--error-strong)", borderColor: "var(--error-strong)", color: "#fff" }}
                  >
                    <Trash2 size={13} aria-hidden="true" />
                    Excluir
                  </Button>
                </div>
              </Card>

              {/* Upload */}
              <Card>
                <h3 style={{ fontSize: "14px", fontWeight: 600, color: "var(--text)", margin: "0 0 12px" }}>
                  Enviar documento
                </h3>
                <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                  <input
                    type="file"
                    id="knowledge-upload"
                    style={{ display: "none" }}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) void handleUpload(file);
                    }}
                  />
                  <Button
                    size="sm"
                    onClick={() => document.getElementById("knowledge-upload")?.click()}
                    disabled={uploading}
                  >
                    <Upload size={13} aria-hidden="true" />
                    {uploading ? "Enviando..." : "Selecionar arquivo"}
                  </Button>
                  {uploading && (
                    <div style={{ flex: 1, height: "6px", background: "var(--bg-elevated)", borderRadius: "3px" }}>
                      <div
                        style={{
                          width: `${uploadProgress}%`,
                          height: "100%",
                          background: "var(--accent)",
                          borderRadius: "3px",
                          transition: "width 0.2s ease",
                        }}
                      />
                    </div>
                  )}
                </div>
              </Card>

              {/* Documentos */}
              <Card>
                <h3 style={{ fontSize: "14px", fontWeight: 600, color: "var(--text)", margin: "0 0 12px" }}>
                  Documentos ({documents.length})
                </h3>
                {docsLoading ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                    {[0, 1].map((i) => (
                      <Skeleton key={i} width="100%" height={40} />
                    ))}
                  </div>
                ) : documents.length === 0 ? (
                  <p style={{ fontSize: "13px", color: "var(--text-muted)", margin: 0 }}>
                    Nenhum documento ainda. Envie um arquivo para começar.
                  </p>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                    {documents.map((doc) => (
                      <div
                        key={doc.id}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          padding: "10px 12px",
                          background: "var(--bg-elevated)",
                          borderRadius: "var(--radius-sm)",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                          {doc.status === "processing" ? (
                            <Clock size={14} aria-hidden="true" style={{ color: "var(--warning)" }} />
                          ) : doc.status === "ready" ? (
                            <CheckCircle2 size={14} aria-hidden="true" style={{ color: "var(--success)" }} />
                          ) : (
                            <XCircle size={14} aria-hidden="true" style={{ color: "var(--error)" }} />
                          )}
                          <span style={{ fontSize: "13px", color: "var(--text)" }}>{doc.name}</span>
                        </div>
                        <Badge
                          status={doc.status === "ready" ? "success" : doc.status === "processing" ? "warning" : "error"}
                          label={DOC_STATUS_LABELS[doc.status] ?? doc.status}
                        />
                      </div>
                    ))}
                  </div>
                )}
              </Card>

              {/* Consulta de teste */}
              <Card>
                <h3 style={{ fontSize: "14px", fontWeight: 600, color: "var(--text)", margin: "0 0 12px" }}>
                  Consulta de teste
                </h3>
                <div style={{ display: "flex", gap: "8px" }}>
                  <Input
                    id="knowledge-query"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void handleQuery();
                    }}
                    placeholder="Digite uma pergunta para testar a busca..."
                    disabled={queryBusy}
                  />
                  <Button size="sm" variant="primary" onClick={() => void handleQuery()} loading={queryBusy}>
                    <Search size={13} aria-hidden="true" />
                    Buscar
                  </Button>
                </div>
                {queryError && (
                  <p role="alert" style={{ fontSize: "12px", color: "var(--error)", margin: "8px 0 0" }}>
                    {queryError}
                  </p>
                )}
                {queryDone && queryResults.length === 0 && (
                  <p role="status" style={{ fontSize: "12px", color: "var(--text-muted)", margin: "8px 0 0" }}>
                    Nenhum trecho acima do limiar de similaridade da base. Reformule a pergunta ou reduza o limiar.
                  </p>
                )}
                {queryResults.length > 0 && (
                  <div style={{ marginTop: "12px", display: "flex", flexDirection: "column", gap: "8px" }}>
                    {queryResults.map((result, i) => (
                      <div
                        key={i}
                        style={{
                          padding: "10px 12px",
                          background: "var(--bg-elevated)",
                          borderRadius: "var(--radius-sm)",
                          border: "1px solid var(--border-subtle)",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                          <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>{result.source}</span>
                          <Badge status="neutral" label={`Score: ${result.score.toFixed(2)}`} />
                        </div>
                        <p style={{ fontSize: "13px", color: "var(--text)", margin: 0 }}>{result.content}</p>
                      </div>
                    ))}
                  </div>
                )}
              </Card>

              {/* Rivvn (desabilitado) */}
              <Card style={{ opacity: 0.6 }}>
                <h3 style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-muted)", margin: "0 0 8px" }}>
                  Integração Rivvn
                </h3>
                <p style={{ fontSize: "12px", color: "var(--text-muted)", margin: 0 }}>
                  A integração com Rivvn está disponível apenas para clientes com contrato ativo.
                  Entre em contato com o comercial para habilitar.
                </p>
              </Card>
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div>
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

      {/* Modal confirmar exclusão */}
      <Modal
        open={deleteModalOpen}
        onClose={() => setDeleteModalOpen(false)}
        title="Excluir base de conhecimento"
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
          Excluir a base <strong>{deleting?.name}</strong>? Todos os documentos serão removidos.
        </p>
      </Modal>
    </div>
  );
}
