"use client";

import * as React from "react";
import { MoreVertical } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Pipeline } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { useToast } from "@/components/ui/toast";

/**
 * PipelineActionsMenu (Task 10, review round 1 item 3).
 * Menu "Mais ações" (Duplicar/Excluir) + confirmação de exclusão no `Modal`.
 * Compartilhado entre o cabeçalho do editor (pipeline-header.tsx) e o card da
 * lista de pipelines (app/(dashboard)/pipelines/page.tsx) para não duplicar a
 * lógica de abrir/fechar (Esc, clique fora) e as chamadas de API.
 *
 * Chama DELETE /api/pipelines/{id} e POST /api/pipelines/{id}/duplicate
 * diretamente; o sucesso é comunicado ao chamador via onDeleted/onDuplicated
 * (toast de sucesso e navegação/refetch ficam por conta de quem usa o menu,
 * já que variam entre o editor e a lista). Erros são mostrados aqui via toast.
 */
export interface PipelineActionsMenuProps {
  pipelineId: string;
  pipelineName: string;
  /** aria-label do botão gatilho e do menu; default "Mais ações". */
  label?: string;
  onDuplicated: (id: string) => void;
  onDeleted: () => void;
}

export function PipelineActionsMenu({
  pipelineId,
  pipelineName,
  label = "Mais ações",
  onDuplicated,
  onDeleted,
}: PipelineActionsMenuProps) {
  const { addToast } = useToast();

  const [menuOpen, setMenuOpen] = React.useState(false);
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const [deleting, setDeleting] = React.useState(false);
  const [duplicating, setDuplicating] = React.useState(false);

  const menuRef = React.useRef<HTMLDivElement>(null);
  const menuButtonRef = React.useRef<HTMLButtonElement>(null);

  async function handleDelete() {
    setDeleting(true);
    try {
      await api.delete(`/api/pipelines/${pipelineId}`);
      setConfirmDelete(false);
      onDeleted();
    } catch (e) {
      addToast("error", e instanceof ApiError ? e.message : "Não foi possível excluir o pipeline.");
    } finally {
      setDeleting(false);
    }
  }

  async function handleDuplicate() {
    setMenuOpen(false);
    setDuplicating(true);
    try {
      const res = await api.post<Pipeline>(`/api/pipelines/${pipelineId}/duplicate`);
      addToast("success", "Pipeline duplicado.");
      onDuplicated(res.id);
    } catch (e) {
      addToast("error", e instanceof ApiError ? e.message : "Não foi possível duplicar o pipeline.");
    } finally {
      setDuplicating(false);
    }
  }

  // Esc/clique fora fecham o menu.
  React.useEffect(() => {
    if (!menuOpen) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setMenuOpen(false);
        menuButtonRef.current?.focus();
      }
    }
    function onClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    }
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onClickOutside);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onClickOutside);
    };
  }, [menuOpen]);

  return (
    // Para de propagar cliques: em contextos onde o menu vive dentro de um
    // container clicável (ex.: o card da lista, que navega ao ser clicado),
    // abrir/usar o menu não deve também disparar a ação do container.
    <div ref={menuRef} style={{ position: "relative" }} onClick={(e) => e.stopPropagation()}>
      <button
        ref={menuButtonRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        aria-label={label}
        onClick={() => setMenuOpen((v) => !v)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: 32,
          height: 32,
          background: "var(--bg-card)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-sm)",
          color: "var(--text)",
          cursor: "pointer",
        }}
      >
        <MoreVertical size={14} aria-hidden="true" />
      </button>
      {menuOpen && (
        <div
          role="menu"
          aria-label={label}
          style={{
            position: "absolute",
            top: "calc(100% + 4px)",
            right: 0,
            zIndex: 20,
            minWidth: 160,
            background: "var(--bg-elevated)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
            boxShadow: "var(--shadow-lg)",
            padding: 4,
            display: "flex",
            flexDirection: "column",
          }}
        >
          <button
            role="menuitem"
            type="button"
            disabled={duplicating}
            onClick={() => void handleDuplicate()}
            style={{
              textAlign: "left",
              padding: "8px 10px",
              background: "none",
              border: "none",
              borderRadius: "var(--radius-sm)",
              color: "var(--text)",
              cursor: "pointer",
              fontSize: 13,
            }}
          >
            Duplicar pipeline
          </button>
          <button
            role="menuitem"
            type="button"
            onClick={() => {
              setMenuOpen(false);
              setConfirmDelete(true);
            }}
            style={{
              textAlign: "left",
              padding: "8px 10px",
              background: "none",
              border: "none",
              borderRadius: "var(--radius-sm)",
              color: "var(--error)",
              cursor: "pointer",
              fontSize: 13,
            }}
          >
            Excluir pipeline
          </button>
        </div>
      )}

      <Modal
        open={confirmDelete}
        title="Excluir pipeline"
        onClose={() => {
          if (!deleting) setConfirmDelete(false);
        }}
        footer={
          <>
            <Button disabled={deleting} onClick={() => setConfirmDelete(false)}>
              Cancelar
            </Button>
            <Button loading={deleting} onClick={() => void handleDelete()}>
              Excluir
            </Button>
          </>
        }
      >
        <p>Excluir o pipeline {pipelineName}? Esta ação não pode ser desfeita.</p>
      </Modal>
    </div>
  );
}
