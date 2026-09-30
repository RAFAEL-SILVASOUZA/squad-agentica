"use client";

import * as React from "react";
import { ApprovalQueue } from "@/components/approvals/approval-queue";
import { Tabs } from "@/components/ui/tabs";

/**
 * Página de aprovações (fe-approvals, Task 16).
 * - Tabs: Pendentes / Respondidas.
 * - ApprovalQueue: fila com contexto, ações inline e modal de ajuda.
 * - onPendingCountChange atualiza o badge da sidebar/topbar via layout.
 */
export default function ApprovalsPage() {
  const [pendingCount, setPendingCount] = React.useState(0);
  const [activeTab, setActiveTab] = React.useState("pending");

  const handlePendingCountChange = React.useCallback((count: number) => {
    setPendingCount(count);
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
      <Tabs
        tabs={[
          { id: "pending", label: `Pendentes${pendingCount > 0 ? ` (${pendingCount})` : ""}` },
          { id: "resolved", label: "Respondidas" },
        ]}
        activeTab={activeTab}
        onTabChange={setActiveTab}
      />
      <div style={{ marginTop: "16px" }}>
        <ApprovalQueue
          status={activeTab === "pending" ? "pending" : "resolved"}
          onPendingCountChange={activeTab === "pending" ? handlePendingCountChange : undefined}
        />
      </div>
    </div>
  );
}
