"use client";

import { ApprovalQueue } from "./approval-queue";

/**
 * ApprovalPanel (fe-approvals, design system §3.6).
 * Wrapper fino que delega para ApprovalQueue (Task 16).
 * Mantém a interface pública para compatibilidade.
 */

export interface ApprovalPanelProps {
  /**
   * Callback opcional chamado quando a contagem de pendentes muda.
   * Usado pelo layout do dashboard para atualizar o badge da sidebar/topbar.
   */
  onPendingCountChange?: (count: number) => void;
}

export function ApprovalPanel({ onPendingCountChange }: ApprovalPanelProps) {
  return <ApprovalQueue status="pending" onPendingCountChange={onPendingCountChange} />;
}
