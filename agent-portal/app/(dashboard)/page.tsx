"use client";

import { Bot } from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";
import { Button } from "@/components/ui/button";
import Link from "next/link";

/**
 * Placeholder do dashboard (fe-dashboard substitui).
 * Portal nasce vazio (contrato §0): sem seed ilustrativo.
 */
export default function DashboardPage() {
  return (
    <div>
      <h1
        style={{
          fontSize: "20px",
          fontWeight: 700,
          color: "var(--text)",
          margin: "0 0 24px",
        }}
      >
        Dashboard
      </h1>
      <EmptyState
        icon={Bot}
        title="Nenhum agente ainda"
        description="Crie seu primeiro agente para começar a montar pipelines."
        action={
          <Link href="/agents/new">
            <Button variant="primary">Criar primeiro agente</Button>
          </Link>
        }
      />
    </div>
  );
}
