"use client";

import * as React from "react";
import { signOut, useSession } from "next-auth/react";
import { Sun, Moon, LogOut, Bell } from "lucide-react";

/**
 * Topbar do shell (design system §2.13).
 * Logo + toggle de tema + avatar + logout + sino de notificações.
 */

interface AppTopbarProps {
  pendingApprovals?: number;
  onNotificationsClick?: () => void;
}

export function AppTopbar({
  pendingApprovals = 0,
  onNotificationsClick,
}: AppTopbarProps) {
  const { data: session } = useSession();
  const [theme, setTheme] = React.useState<"dark" | "light">("dark");
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
    const stored =
      typeof window !== "undefined"
        ? (localStorage.getItem("agent-portal-theme") as "dark" | "light" | null)
        : null;
    if (stored === "dark" || stored === "light") {
      setTheme(stored);
      document.documentElement.setAttribute("data-theme", stored);
    }
  }, []);

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("agent-portal-theme", next);
  };

  const handleLogout = async () => {
    await signOut({ callbackUrl: "/login" });
  };

  const userInitials = React.useMemo(() => {
    if (!session?.user?.name) return "?";
    const parts = session.user.name.split(" ");
    if (parts.length >= 2) {
      return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    }
    return session.user.name.slice(0, 2).toUpperCase();
  }, [session?.user?.name]);

  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 20px",
        background: "var(--bg-elevated)",
        borderBottom: "1px solid var(--border)",
        zIndex: 10,
        height: 56,
        flexShrink: 0,
      }}
    >
      {/* Logo */}
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <span
          aria-hidden="true"
          style={{
            width: 30,
            height: 30,
            borderRadius: "var(--radius-sm)",
            background: "var(--accent)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#fff",
            fontSize: "14px",
            fontWeight: 700,
          }}
        >
          AP
        </span>
        <span
          style={{
            fontSize: "13px",
            fontWeight: 600,
            color: "var(--text)",
          }}
        >
          Agent Portal
          <span
            style={{
              fontSize: "11px",
              fontWeight: 400,
              color: "var(--text-muted)",
              marginLeft: 6,
            }}
          >
            V1
          </span>
        </span>
      </div>

      {/* Right side */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        {/* Notification bell */}
        <button
          onClick={onNotificationsClick}
          aria-label={
            pendingApprovals > 0
              ? `${pendingApprovals} aprovações pendentes`
              : "Notificações"
          }
          style={{
            width: 36,
            height: 36,
            borderRadius: "50%",
            border: "1px solid var(--border)",
            background: "var(--bg-card)",
            color: "var(--text-secondary)",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            position: "relative",
            transition:
              "border-color var(--transition), color var(--transition), background var(--transition)",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = "var(--accent)";
            e.currentTarget.style.color = "var(--accent)";
            e.currentTarget.style.background = "var(--accent-subtle)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = "var(--border)";
            e.currentTarget.style.color = "var(--text-secondary)";
            e.currentTarget.style.background = "var(--bg-card)";
          }}
        >
          <Bell size={16} aria-hidden="true" />
          {pendingApprovals > 0 && (
            <span
              aria-hidden="true"
              style={{
                position: "absolute",
                top: -2,
                right: -2,
                width: 16,
                height: 16,
                borderRadius: "50%",
                background: "var(--accent)",
                color: "#fff",
                fontSize: "9px",
                fontWeight: 700,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {pendingApprovals > 9 ? "9+" : pendingApprovals}
            </span>
          )}
        </button>

        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          aria-label={theme === "dark" ? "Mudar para tema claro" : "Mudar para tema escuro"}
          style={{
            width: 36,
            height: 36,
            borderRadius: "50%",
            border: "1px solid var(--border)",
            background: "var(--bg-card)",
            color: "var(--text-secondary)",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            transition:
              "border-color var(--transition), color var(--transition), background var(--transition)",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = "var(--accent)";
            e.currentTarget.style.color = "var(--accent)";
            e.currentTarget.style.background = "var(--accent-subtle)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = "var(--border)";
            e.currentTarget.style.color = "var(--text-secondary)";
            e.currentTarget.style.background = "var(--bg-card)";
          }}
        >
          {mounted && theme === "dark" ? (
            <Sun size={16} aria-hidden="true" />
          ) : (
            <Moon size={16} aria-hidden="true" />
          )}
        </button>

        {/* Avatar */}
        <div
          aria-label={`Usuário: ${session?.user?.name ?? "desconhecido"}`}
          style={{
            width: 32,
            height: 32,
            borderRadius: "50%",
            border: "2px solid var(--accent)",
            color: "var(--accent)",
            background: "var(--accent-subtle)",
            fontSize: "12px",
            fontWeight: 600,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {userInitials}
        </div>

        {/* Logout */}
        <button
          onClick={handleLogout}
          aria-label="Sair"
          style={{
            width: 36,
            height: 36,
            borderRadius: "50%",
            border: "1px solid var(--border)",
            background: "var(--bg-card)",
            color: "var(--text-secondary)",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            transition:
              "border-color var(--transition), color var(--transition), background var(--transition)",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = "var(--error)";
            e.currentTarget.style.color = "var(--error)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = "var(--border)";
            e.currentTarget.style.color = "var(--text-secondary)";
          }}
        >
          <LogOut size={16} aria-hidden="true" />
        </button>
      </div>
    </header>
  );
}
