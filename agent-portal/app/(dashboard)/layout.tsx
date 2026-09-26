"use client";

import * as React from "react";
import { AppShell } from "@/components/layout/app-shell";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";

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
