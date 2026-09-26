"use client";

import * as React from "react";
import { AppShell } from "@/components/layout/app-shell";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { ApprovalRequest } from "@/lib/types";

/**
 * Layout do grupo autenticado (dashboard).
 * Envolve todas as rotas de (dashboard) com o AppShell.
 * Redireciona para /login se não houver sessão.
 */
export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { data: session, status } = useSession();
  const router = useRouter();
  const [pendingApprovals, setPendingApprovals] = React.useState(0);

  React.useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/login");
    }
  }, [status, router]);

  // Badge de aprovações pendentes (fe-approvals, contrato §2.14).
  // 1) Fetch inicial via REST para popular o badge ao carregar o shell.
  // 2) Listener de evento custom disparado pela página /approvals
  //    quando a contagem muda (aprovar/rejeitar/cancelar).
  React.useEffect(() => {
    if (status !== "authenticated") return;

    let cancelled = false;

    // Fetch inicial: contagem de aprovações pendentes.
    api
      .list<ApprovalRequest>("/api/approvals", {
        page: 1,
        limit: 1,
        query: { status: "pending" },
      })
      .then((res) => {
        if (!cancelled) setPendingApprovals(res.total);
      })
      .catch(() => {
        // WS indisponível ou erro: badge fica em 0 (não bloqueia o shell).
      });

    // Listener: a página /approvals dispara "approvals:pending-count"
    // quando o usuário responde/cancela uma aprovação.
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as { count: number } | undefined;
      if (detail && typeof detail.count === "number") {
        setPendingApprovals(detail.count);
      }
    };
    window.addEventListener("approvals:pending-count", handler);

    return () => {
      cancelled = true;
      window.removeEventListener("approvals:pending-count", handler);
    };
  }, [status]);

  if (status === "loading" || !session) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "100vh",
          background: "var(--bg)",
        }}
      >
        <span
          aria-hidden="true"
          style={{
            width: 24,
            height: 24,
            border: "3px solid var(--border)",
            borderTopColor: "var(--accent)",
            borderRadius: "50%",
            display: "inline-block",
            animation: "spin 1s linear infinite",
          }}
        />
      </div>
    );
  }

  return (
    <AppShell
      pendingApprovals={pendingApprovals}
      onNotificationsClick={() => {
        router.push("/approvals");
      }}
    >
      {children}
    </AppShell>
  );
}
