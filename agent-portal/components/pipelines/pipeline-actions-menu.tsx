"use client";

import * as React from "react";
import { MoreVertical } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Pipeline } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Popover } from "@/components/ui/popover";
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
export interface PipelineActionsMenuExtraItem {
  label: string;
  action: string;
}

export interface PipelineActionsMenuProps {
  pipelineId: string;
  pipelineName: string;
  /** aria-label do botão gatilho e do menu; default "Mais ações". */
  label?: string;
  onDuplicated: (id: string) => void;
  onDeleted: () => void;
  /**
   * Ações extras renderizadas no topo do menu (ex.: "Abrir"/"Monitor" na lista
   * de pipelines). Opcional: o cabeçalho do editor não passa e mostra só
   * Duplicar/Excluir. Mantém um único menu ⋮ por linha (spec: "menu ⋮ por linha").
   */
  extraItems?: PipelineActionsMenuExtraItem[];
  onExtraAction?: (action: string) => void;
}

export function PipelineActionsMenu({
  pipelineId,
  pipelineName,
  label = "Mais ações",
  onDuplicated,
  onDeleted,
  extraItems,
  onExtraAction,
}: PipelineActionsMenuProps) {
  const { addToast } = useToast();

  const [menuOpen, setMenuOpen] = React.useState(false);
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const [deleting, setDeleting] = React.useState(false);
  const [duplicating, setDuplicating] = React.useState(false);

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



  return (
    <div onClick={(e) => e.stopPropagation()}>
      <button
        ref={menuButtonRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        aria-label={label}
        onClick={(e) => {
          e.stopPropagation();
          setMenuOpen((v) => !v);
        }}
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          color: "var(--text-muted)",
          padding: "4px",
          display: "flex",
          alignItems: "center",
        }}
      >
        <MoreVertical size={14} aria-hidden="true" />
      </button>
      <Popover open={menuOpen} onClose={() => setMenuOpen(false)} anchorRef={menuButtonRef} align="end" minWidth={180}>
        {extraItems?.map((item) => (
          <button
            key={item.action}
            role="menuitem"
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setMenuOpen(false);
              onExtraAction?.(item.action);
            }}
            style={{
              display: "block",
              width: "100%",
              padding: "8px 12px",
              fontSize: "12px",
              textAlign: "left",
              background: "none",
              border: "none",
              cursor: "pointer",
              color: "var(--text)",
              whiteSpace: "nowrap",
            }}
          >
            {item.label}
          </button>
        ))}
        <button
          role="menuitem"
          type="button"
          disabled={duplicating}
          onClick={(e) => {
            e.stopPropagation();
            void handleDuplicate();
          }}
          style={{
            display: "block",
            width: "100%",
            padding: "8px 12px",
            fontSize: "12px",
            textAlign: "left",
            background: "none",
            border: "none",
            cursor: "pointer",
            color: "var(--text)",
            whiteSpace: "nowrap",
          }}
        >
          Duplicar pipeline
        </button>
        <button
          role="menuitem"
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setMenuOpen(false);
            setConfirmDelete(true);
          }}
          style={{
            display: "block",
            width: "100%",
            padding: "8px 12px",
            fontSize: "12px",
            textAlign: "left",
            background: "none",
            border: "none",
            cursor: "pointer",
            color: "var(--error)",
            whiteSpace: "nowrap",
          }}
        >
          Excluir pipeline
        </button>
      </Popover>

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
