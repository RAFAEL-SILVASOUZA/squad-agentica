"use client";

import * as React from "react";
import { AppShell } from "@/components/layout/app-shell";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { getWebSocketClient, disposeWebSocketClient } from "@/lib/websocket";
import { SkeletonShell } from "@/components/ui/skeleton";
import type { ApprovalRequest, ApprovalNewEvent, ApprovalResolvedEvent } from "@/lib/types";

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

  // Badge de aprovações pendentes (fe-approvals, contrato §7).
  // 1) Fetch inicial via REST para popular o badge ao carregar o shell.
  // 2) WebSocket: approval:new incrementa, approval:resolved decrementa.
  // 3) Ao reconectar, refetch REST (contrato §7).
  // 4) Listener de evento custom disparado pela página /approvals
  //    quando a contagem muda (aprovar/rejeitar/cancelar), mantendo o
  //    badge sincronizado sem depender do estado local do painel.
  React.useEffect(() => {
    if (status !== "authenticated") return;

    let cancelled = false;
    let wsClient: ReturnType<typeof getWebSocketClient> | null = null;

    const fetchCount = () =>
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
          // Erro no fetch: badge mantém o último valor (não bloqueia o shell).
        });

    void fetchCount();

    // WebSocket (contrato §7): eventos em tempo real para o badge.
    const connectWs = async () => {
      try {
        const tokenRes = await fetch("/api/session-token", {
          method: "GET",
          credentials: "same-origin",
        });
        if (!tokenRes.ok) return;
        const { accessToken } = (await tokenRes.json()) as {
          accessToken: string;
        };
        wsClient = getWebSocketClient(accessToken);

        const onNew = (eventData: Record<string, unknown>) => {
          const event = eventData as unknown as ApprovalNewEvent;
          if (typeof event.approvalId !== "string") return;
          setPendingApprovals((prev) => prev + 1);
        };

        const onResolved = (eventData: Record<string, unknown>) => {
          const event = eventData as unknown as ApprovalResolvedEvent;
          if (typeof event.approvalId !== "string") return;
          setPendingApprovals((prev) => Math.max(0, prev - 1));
        };

        wsClient.on("approval:new", onNew);
        wsClient.on("approval:resolved", onResolved);
        wsClient.onReconnect(() => {
          void fetchCount();
        });
        wsClient.connect();
      } catch {
        // WS indisponível: o badge segue apenas com REST.
      }
    };

    void connectWs();

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
      disposeWebSocketClient();
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
        <SkeletonShell />
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
