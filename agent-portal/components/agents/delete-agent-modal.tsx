"use client";

import * as React from "react";
import { Trash2 } from "lucide-react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";

/**
 * Modal de confirmação de exclusão de agente (sem window.confirm).
 *
 * Sem emojis; ícone via lucide-react.
 */

export interface DeleteAgentModalProps {
  open: boolean;
  /** Nome do agente (para exibir na mensagem). */
  agentName: string;
  /** true enquanto exclui. */
  deleting?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function DeleteAgentModal({
  open,
  agentName,
  deleting = false,
  onConfirm,
  onCancel,
}: DeleteAgentModalProps) {
  return (
    <Modal
      open={open}
      onClose={onCancel}
      title="Excluir agente"
      footer={
        <>
          <Button onClick={onCancel} disabled={deleting}>
            Cancelar
          </Button>
          <Button
            variant="primary"
            onClick={onConfirm}
            loading={deleting}
            style={{
              background: "var(--error)",
              borderColor: "var(--error)",
            }}
          >
            <Trash2 size={14} aria-hidden="true" />
            Excluir
          </Button>
        </>
      }
    >
      <p
        style={{
          fontSize: "13px",
          color: "var(--text)",
          margin: 0,
          lineHeight: 1.5,
        }}
      >
        Tem certeza que deseja excluir o agente{" "}
        <strong style={{ fontWeight: 600 }}>{agentName}</strong>? Esta ação não
        pode ser desfeita.
      </p>
    </Modal>
  );
}
