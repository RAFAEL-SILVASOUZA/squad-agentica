"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Card } from "@/components/ui/card";
import { GitConnections } from "./git-connections";

const tabs = [{ id: "github", label: "GitHub" }, { id: "azure", label: "Azure DevOps" }, { id: "outras", label: "Outras" }] as const;
type Tab = typeof tabs[number]["id"];
function validTab(value: string | null): Tab { return value === "azure" || value === "outras" ? value : "github"; }

export function IntegrationsView() {
  const router = useRouter();
  const params = useSearchParams();
  const queryTab = params.get("tab");
  const [active, setActive] = React.useState<Tab>(() => validTab(queryTab));
  React.useEffect(() => { setActive(validTab(queryTab)); }, [queryTab]);
  function select(tab: Tab) {
    setActive(tab);
    const next = new URLSearchParams(params.toString()); next.set("tab", tab);
    router.replace(`/integrations?${next}`, { scroll: false });
  }
  return <div style={{ display: "grid", gap: 20 }}>
    <h1 style={{ margin: 0, fontSize: 24 }}>Integrações</h1>
    <div role="tablist" aria-label="Provedores de integração" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      {tabs.map((tab, index) => <button key={tab.id} id={`tab-${tab.id}`} role="tab" aria-selected={active === tab.id} aria-controls={`panel-${tab.id}`} tabIndex={active === tab.id ? 0 : -1}
        onClick={() => select(tab.id)} onKeyDown={(event) => {
          if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
          event.preventDefault();
          const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
          select(tabs[next].id); document.getElementById(`tab-${tabs[next].id}`)?.focus();
        }} style={{ padding: "10px 16px", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)", background: active === tab.id ? "var(--accent-subtle)" : "var(--bg-card)", color: active === tab.id ? "var(--accent)" : "var(--text)", cursor: "pointer" }}>{tab.label}</button>)}
    </div>
    <div role="tabpanel" id={`panel-${active}`} aria-labelledby={`tab-${active}`} tabIndex={0}>
      {active === "outras" ? <Card style={{ opacity: 0.6 }}>
        <h3 style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-muted)", margin: "0 0 8px" }}>Integração Rivvn</h3>
        <p style={{ fontSize: "12px", color: "var(--text-muted)", margin: 0 }}>
          A integração com Rivvn está disponível apenas para clientes com contrato ativo.
          Entre em contato com o comercial para habilitar.
        </p>
      </Card> : <GitConnections key={active} provider={active} />}
    </div>
  </div>;
}
