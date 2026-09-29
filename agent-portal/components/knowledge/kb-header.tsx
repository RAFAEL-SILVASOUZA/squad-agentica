"use client";

import * as React from "react";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Modal } from "@/components/ui/modal";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api";
import type { KnowledgeBaseItem } from "./types";

/**
 * KbHeader: nome e descrição da base editáveis inline (mesmo padrão do
 * PipelineHeader) e exclusão com confirmação. Cada campo alterado vira um
 * PUT /api/knowledge/{id} só com esse campo.
 */
export interface KbHeaderProps {
  base: KnowledgeBaseItem;
  onUpdated: (base: KnowledgeBaseItem) => void;
  onDeleted: () => void;
}

const FIELD_STYLE: React.CSSProperties = {
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-sm)",
  padding: "4px 8px",
  width: "100%",
  fontFamily: "var(--font)",
  background: "var(--bg-elevated)",
};

export function KbHeader({ base, onUpdated, onDeleted }: KbHeaderProps) {
  const { addToast } = useToast();
  const [editingName, setEditingName] = React.useState(false);
  const [nameValue, setNameValue] = React.useState(base.name);
  const [nameError, setNameError] = React.useState("");
  const [editingDescription, setEditingDescription] = React.useState(false);
  const [descriptionValue, setDescriptionValue] = React.useState(base.description ?? "");
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [deleteBusy, setDeleteBusy] = React.useState(false);

  // Buffers em sincronia com a base, exceto durante a edição do campo.
  React.useEffect(() => {
    if (!editingName) setNameValue(base.name);
  }, [base.name, editingName]);
  React.useEffect(() => {
    if (!editingDescription) setDescriptionValue(base.description ?? "");
  }, [base.description, editingDescription]);

  async function save(patch: { name?: string; description?: string }) {
    try {
      const updated = await api.put<Partial<KnowledgeBaseItem>>(`/api/knowledge/${base.id}`, patch);
      onUpdated({ ...base, ...patch, ...updated });
    } catch (e) {
      addToast("error", e instanceof ApiError ? e.message : "Não foi possível salvar a base.");
      setNameValue(base.name);
      setDescriptionValue(base.description ?? "");
    }
  }

  function commitName() {
    const trimmed = nameValue.trim();
    if (!trimmed) {
      setNameError("Informe um nome para a base.");
      return;
    }
    setNameError("");
    setEditingName(false);
    if (trimmed !== base.name) void save({ name: trimmed });
  }

  function cancelName() {
    setNameValue(base.name);
    setNameError("");
    setEditingName(false);
  }

  function commitDescription() {
    setEditingDescription(false);
    if (descriptionValue !== (base.description ?? "")) void save({ description: descriptionValue });
  }

  function cancelDescription() {
    setDescriptionValue(base.description ?? "");
    setEditingDescription(false);
  }

  async function handleDelete() {
    setDeleteBusy(true);
    try {
      await api.delete(`/api/knowledge/${base.id}`);
      addToast("info", "Base de conhecimento excluída");
      setConfirmOpen(false);
      onDeleted();
    } catch (e) {
      addToast("error", e instanceof ApiError ? e.message : "Erro ao excluir base");
    } finally {
      setDeleteBusy(false);
    }
  }

  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: 220 }}>
          {editingName ? (
            <div>
              <input
                aria-label="Nome da base"
                value={nameValue}
                autoFocus
                onChange={(e) => setNameValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commitName();
                  if (e.key === "Escape") cancelName();
                }}
                onBlur={commitName}
                style={{ ...FIELD_STYLE, fontSize: 16, fontWeight: 700, color: "var(--text)" }}
              />
              {nameError && (
                <p role="alert" style={{ color: "var(--error)", fontSize: 12, margin: "4px 0 0" }}>
                  {nameError}
                </p>
              )}
            </div>
          ) : (
            <h2
              onClick={() => setEditingName(true)}
              title="Clique para editar o nome"
              style={{ fontSize: 16, fontWeight: 700, color: "var(--text)", margin: 0, cursor: "pointer" }}
            >
              {base.name}
            </h2>
          )}

          {editingDescription ? (
            <textarea
              aria-label="Descrição da base"
              value={descriptionValue}
              autoFocus
              rows={1}
              onChange={(e) => setDescriptionValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  commitDescription();
                }
                if (e.key === "Escape") cancelDescription();
              }}
              onBlur={commitDescription}
              style={{ ...FIELD_STYLE, fontSize: 12, color: "var(--text-secondary)", marginTop: 4, resize: "none" }}
            />
          ) : (
            <p
              onClick={() => setEditingDescription(true)}
              title="Clique para editar a descrição"
              style={{ fontSize: 12, color: "var(--text-secondary)", margin: "4px 0 0", cursor: "pointer", minHeight: 16 }}
            >
              {base.description || "Adicionar descrição"}
            </p>
          )}
        </div>
        <Button
          size="sm"
          onClick={() => setConfirmOpen(true)}
          style={{ background: "var(--error-strong)", borderColor: "var(--error-strong)", color: "#fff" }}
        >
          <Trash2 size={13} aria-hidden="true" />
          Excluir base
        </Button>
      </div>

      <Modal
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Excluir base de conhecimento"
        footer={
          <>
            <Button size="sm" onClick={() => setConfirmOpen(false)} disabled={deleteBusy}>
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
        <p style={{ fontSize: 13, color: "var(--text)", margin: 0 }}>
          Excluir a base <strong>{base.name}</strong>? Todos os documentos e conversas serão removidos.
        </p>
      </Modal>
    </Card>
  );
}
