"use client";

import * as React from "react";
import { ApprovalPanel } from "@/components/approvals/approval-panel";

/**
 * Página de aprovações (fe-approvals, protótipo view-approvals).
 * - Header: título + subtítulo com contexto.
 * - ApprovalPanel: fila de pendentes + ações aprovar/rejeitar/argumentar/cancelar.
 * - onPendingCountChange atualiza o badge da sidebar/topbar via layout.
 *
 * Portal nasce vazio (contrato §0): sem seed ilustrativo.
 */
export default function ApprovalsPage() {
  const [pendingCount, setPendingCount] = React.useState(0);

  // O layout do dashboard consome pendingCount via contexto ou prop.
  // Aqui usamos um callback que o layout injeta via React context.
  const handlePendingCountChange = React.useCallback((count: number) => {
    setPendingCount(count);
    // Dispara um evento custom para o layout ouvir (evita prop drilling).
    if (typeof window !== "undefined") {
      window.dispatchEvent(
        new CustomEvent("approvals:pending-count", { detail: { count } })
      );
    }
  }, []);

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: "16px",
          marginBottom: "20px",
          flexWrap: "wrap",
        }}
      >
        <div>
          <h1
            style={{
              fontSize: "20px",
              fontWeight: 700,
              color: "var(--text)",
              margin: 0,
            }}
          >
            Aprovações
          </h1>
          <p
            style={{
              fontSize: "12px",
              color: "var(--text-secondary)",
              margin: "4px 0 0",
            }}
          >
            {pendingCount > 0
              ? `${pendingCount} ${pendingCount === 1 ? "agente aguardando" : "agentes aguardando"} sua decisão`
              : "Fila de aprovações pendentes"}
          </p>
        </div>
      </div>
      <ApprovalPanel onPendingCountChange={handlePendingCountChange} />
    </div>
  );
}
