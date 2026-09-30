"use client";

import * as React from "react";
import { Upload, Trash2, CheckCircle2, XCircle, Clock, Eye } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { ErrorPanel } from "@/components/ui/error-panel";
import { api, ApiError } from "@/lib/api";
import { DocumentDrawer, type DocumentDetail } from "./document-drawer";
import type { KnowledgeDocument } from "./types";

/**
 * DocumentsPanel: upload (com tratamento do 409 duplicate_document) e lista
 * de documentos com "Remover" e confirmação. `onCountChange` informa a nova
 * contagem para a lista de bases.
 */
export interface DocumentsPanelProps {
  baseId: string;
  onCountChange: (count: number) => void;
}

const DOC_STATUS_LABELS: Record<string, string> = {
  processing: "Processando",
  ready: "Pronto",
  failed: "Falhou",
};

interface DuplicateInfo {
  file: File;
  documentId: string;
  name: string;
}

export function DocumentsPanel({ baseId, onCountChange }: DocumentsPanelProps) {
  const { addToast } = useToast();
  const [documents, setDocuments] = React.useState<KnowledgeDocument[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [uploading, setUploading] = React.useState(false);
  const [uploadProgress, setUploadProgress] = React.useState(0);
  const [duplicate, setDuplicate] = React.useState<DuplicateInfo | null>(null);
  const [removing, setRemoving] = React.useState<KnowledgeDocument | null>(null);
  const [removeBusy, setRemoveBusy] = React.useState(false);
  const [viewing, setViewing] = React.useState<DocumentDetail | null>(null);
  const [viewLoading, setViewLoading] = React.useState(false);
  const [viewError, setViewError] = React.useState<string | null>(null);
  // Descarta respostas de cliques superados (dois cliques rápidos em "Ver").
  const viewSeq = React.useRef(0);
  // Falha no upload: bloqueia a ação principal, então fica inline com retry.
  const [uploadError, setUploadError] = React.useState<{ message: string; detail?: string } | null>(null);
  const uploadRetryRef = React.useRef<{ file: File; replaceId?: string } | null>(null);
  const baseIdRef = React.useRef(baseId);
  baseIdRef.current = baseId;
  const onCountRef = React.useRef(onCountChange);
  onCountRef.current = onCountChange;

  const loadDocuments = React.useCallback(async () => {
    setLoading(true);
    try {
      // Lista paginada (contrato §8): os itens vêm em ``items``.
      const res = await api.list<KnowledgeDocument>(`/api/knowledge/${baseId}/documents`, { page: 1, limit: 100 });
      if (baseIdRef.current !== baseId) return null; // resposta de outra base
      setDocuments(res.items);
      return res.items.length;
    } catch (e) {
      addToast("error", e instanceof ApiError ? e.message : "Erro ao carregar documentos");
      return null;
    } finally {
      setLoading(false);
    }
  }, [baseId, addToast]);

  React.useEffect(() => {
    void loadDocuments();
  }, [loadDocuments]);

  const upload = React.useCallback(
    async (file: File, replaceId?: string) => {
      setUploading(true);
      setUploadProgress(0);
      const formData = new FormData();
      formData.append("file", file);
      // Progresso simulado: fetch não expõe o progresso do upload.
      const interval = setInterval(() => setUploadProgress((p) => Math.min(p + 10, 90)), 200);
      try {
        // E10: nunca fixar Content-Type em FormData (o browser insere o boundary).
        const suffix = replaceId ? `?replace=${encodeURIComponent(replaceId)}` : "";
        await api.post(`/api/knowledge/${baseId}/upload${suffix}`, formData);
        setUploadProgress(100);
        addToast("success", replaceId ? "Documento substituído" : "Documento enviado para ingestão");
        const count = await loadDocuments();
        if (count !== null) onCountRef.current(count);
      } catch (e) {
        if (e instanceof ApiError && e.code === "duplicate_document") {
          const details = e.details as { documentId?: string; name?: string } | undefined;
          if (details?.documentId) {
            setDuplicate({ file, documentId: details.documentId, name: details.name ?? "documento existente" });
            return;
          }
        }
        setUploadError({
          message: "Não foi possível enviar o documento",
          detail: e instanceof ApiError ? e.describe() : undefined,
        });
        uploadRetryRef.current = { file, replaceId };
      } finally {
        clearInterval(interval);
        setUploading(false);
        setUploadProgress(0);
      }
    },
    [baseId, addToast, loadDocuments]
  );

  async function confirmRemove() {
    if (!removing) return;
    setRemoveBusy(true);
    try {
      await api.delete(`/api/knowledge/${baseId}/documents/${removing.id}`);
      const remaining = documents.filter((d) => d.id !== removing.id);
      setDocuments(remaining);
      onCountRef.current(remaining.length);
      addToast("info", "Documento removido");
      setRemoving(null);
    } catch (e) {
      addToast("error", e instanceof ApiError ? e.message : "Erro ao remover documento");
    } finally {
      setRemoveBusy(false);
    }
  }

  return (
    <>
      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: "var(--text)", margin: 0 }}>
            Documentos ({documents.length})
          </h3>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flex: "1 1 160px", justifyContent: "flex-end" }}>
            <input
              type="file"
              id="knowledge-upload"
              style={{ display: "none" }}
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (file) void upload(file);
              }}
            />
            {uploading && (
              <div style={{ flex: 1, maxWidth: 160, height: 6, background: "var(--bg-elevated)", borderRadius: 3 }}>
                <div
                  style={{
                    width: `${uploadProgress}%`,
                    height: "100%",
                    background: "var(--accent)",
                    borderRadius: 3,
                    transition: "width 0.2s ease",
                  }}
                />
              </div>
            )}
            <Button
              size="sm"
              onClick={() => document.getElementById("knowledge-upload")?.click()}
              disabled={uploading}
            >
              <Upload size={13} aria-hidden="true" />
              {uploading ? "Enviando..." : "Selecionar arquivo"}
            </Button>
          </div>
        </div>

        {/* Erro do upload: inline com "Tentar de novo" (reenvia o mesmo arquivo) */}
        {uploadError && (
          <div style={{ marginBottom: 12 }}>
            <ErrorPanel
              title={uploadError.message}
              detail={uploadError.detail}
              onRetry={() => {
                const r = uploadRetryRef.current;
                if (r) void upload(r.file, r.replaceId);
              }}
            />
          </div>
        )}

        {loading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[0, 1].map((i) => (
              <Skeleton key={i} width="100%" height={40} />
            ))}
          </div>
        ) : documents.length === 0 ? (
          <p style={{ fontSize: 13, color: "var(--text-muted)", margin: 0 }}>
            Nenhum documento ainda. Envie um arquivo para começar.
          </p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 320, overflowY: "auto" }}>
            {documents.map((doc) => (
              <div
                key={doc.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 8,
                  padding: "10px 12px",
                  background: "var(--bg-elevated)",
                  borderRadius: "var(--radius-sm)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                  {doc.status === "processing" ? (
                    <Clock size={14} aria-hidden="true" style={{ color: "var(--warning)" }} />
                  ) : doc.status === "ready" ? (
                    <CheckCircle2 size={14} aria-hidden="true" style={{ color: "var(--success)" }} />
                  ) : (
                    <XCircle size={14} aria-hidden="true" style={{ color: "var(--error)" }} />
                  )}
                  <span style={{ fontSize: 13, color: "var(--text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {doc.name}
                  </span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                  <Badge
                    status={doc.status === "ready" ? "success" : doc.status === "processing" ? "warning" : "error"}
                    label={DOC_STATUS_LABELS[doc.status] ?? doc.status}
                  />
                  <Button
                    size="sm"
                    aria-label={`Ver ${doc.name}`}
                    onClick={() => {
                      const seq = ++viewSeq.current;
                      setViewing(null);
                      setViewError(null);
                      setViewLoading(true);
                      void api
                        .get<DocumentDetail>(`/api/knowledge/${baseId}/documents/${doc.id}`)
                        .then((detail) => {
                          if (seq !== viewSeq.current) return;
                          setViewing(detail);
                        })
                        .catch((e) => {
                          if (seq !== viewSeq.current) return;
                          setViewError(e instanceof ApiError ? e.message : "Não foi possível carregar o documento.");
                        })
                        .finally(() => {
                          if (seq !== viewSeq.current) return;
                          setViewLoading(false);
                        });
                    }}
                  >
                    <Eye size={13} aria-hidden="true" />
                    Ver
                  </Button>
                  <Button size="sm" aria-label={`Remover ${doc.name}`} onClick={() => setRemoving(doc)}>
                    <Trash2 size={13} aria-hidden="true" />
                    Remover
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Modal
        open={duplicate !== null}
        onClose={() => setDuplicate(null)}
        title="Arquivo duplicado"
        footer={
          <>
            <Button size="sm" onClick={() => setDuplicate(null)}>
              Cancelar
            </Button>
            <Button
              size="sm"
              variant="primary"
              onClick={() => {
                const d = duplicate;
                setDuplicate(null);
                if (d) void upload(d.file, d.documentId);
              }}
            >
              Substituir
            </Button>
          </>
        }
      >
        <p style={{ fontSize: 13, color: "var(--text)", margin: 0 }}>
          Este arquivo já existe nesta base como <strong>{duplicate?.name}</strong>. Substituir a versão existente?
        </p>
      </Modal>

      <DocumentDrawer
        open={viewing !== null || viewLoading || viewError !== null}
        onClose={() => {
          setViewing(null);
          setViewLoading(false);
          setViewError(null);
        }}
        document={viewing}
        loading={viewLoading}
        error={viewError}
      />

      <Modal
        open={removing !== null}
        onClose={() => setRemoving(null)}
        title="Remover documento"
        footer={
          <>
            <Button size="sm" onClick={() => setRemoving(null)} disabled={removeBusy}>
              Cancelar
            </Button>
            <Button
              size="sm"
              onClick={() => void confirmRemove()}
              loading={removeBusy}
              style={{ background: "var(--error-strong)", borderColor: "var(--error-strong)", color: "#fff" }}
            >
              Remover
            </Button>
          </>
        }
      >
        <p style={{ fontSize: 13, color: "var(--text)", margin: 0 }}>
          Remover <strong>{removing?.name}</strong> da base? Os trechos dele deixam de aparecer nas respostas.
        </p>
      </Modal>
    </>
  );
}
