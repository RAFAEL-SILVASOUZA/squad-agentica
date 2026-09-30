"use client";

import * as React from "react";
import { signOut, useSession } from "next-auth/react";
import { Sun, Moon, LogOut, Bell, ChevronDown } from "lucide-react";
import Link from "next/link";
import { useCreatePipelineAndNavigate } from "@/lib/create-pipeline";

/**
 * Topbar do shell (design system §2.13).
 * Logo + toggle de tema + avatar + logout + sino de notificações.
 */

interface AppTopbarProps {
  pendingApprovals?: number;
  onNotificationsClick?: () => void;
  onOpenHelp?: () => void;
  isMobile?: boolean;
  title?: string;
}

export function AppTopbar({
  pendingApprovals = 0,
  onNotificationsClick,
  onOpenHelp,
  isMobile = false,
  title,
}: AppTopbarProps) {
  const { data: session } = useSession();
  const [theme, setTheme] = React.useState<"dark" | "light">("dark");
  const [mounted, setMounted] = React.useState(false);
  const [newMenuOpen, setNewMenuOpen] = React.useState(false);
  const [moreMenuOpen, setMoreMenuOpen] = React.useState(false);

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

  // Fecha o menu “+ Novo” ao clicar em uma opção ou fora dele.
  React.useEffect(() => {
    if (!newMenuOpen) return;
    const onClick = () => setNewMenuOpen(false);
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, [newMenuOpen]);

  // Fecha o menu “⋯” (mobile) ao clicar fora.
  React.useEffect(() => {
    if (!moreMenuOpen) return;
    const onClick = () => setMoreMenuOpen(false);
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, [moreMenuOpen]);

  // Hook chamado diretamente no corpo do componente (local válido de hook).
  const createPipelineAndNavigate = useCreatePipelineAndNavigate();

  const handleCreatePipeline = () => {
    setNewMenuOpen(false);
    void createPipelineAndNavigate();
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
      {/* Logo + título */}
      <div style={{ display: "flex", alignItems: "center", gap: "8px", minWidth: 0 }}>
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
            flexShrink: 0,
          }}
        >
          AP
        </span>
        {isMobile ? (
          <span
            style={{
              fontSize: "15px",
              fontWeight: 600,
              color: "var(--text)",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {title ?? "Agent Portal"}
          </span>
        ) : (
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
        )}
      </div>

      {/* Right side */}
      {isMobile ? (
        <div style={{ display: "flex", alignItems: "center", gap: "8px", position: "relative" }}>
          {/* ⋯ button (mobile) */}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setMoreMenuOpen((o) => !o);
            }}
            aria-haspopup="menu"
            aria-expanded={moreMenuOpen}
            aria-label="Mais opções"
            style={{
              width: 44,
              height: 44,
              borderRadius: "50%",
              border: "1px solid var(--border)",
              background: "var(--bg-card)",
              color: "var(--text-secondary)",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: "18px",
              fontWeight: 600,
            }}
          >
            ⋯
          </button>

          {moreMenuOpen && (
            <div
              role="menu"
              aria-label="Mais opções"
              style={{
                position: "absolute",
                top: "calc(100% + 6px)",
                right: 0,
                zIndex: 20,
                minWidth: 200,
                padding: "6px",
                background: "var(--bg-elevated)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius)",
                boxShadow: "var(--shadow-md, 0 4px 16px rgba(0,0,0,0.2))",
              }}
            >
              <button
                type="button"
                role="menuitem"
                onClick={() => { setMoreMenuOpen(false); onNotificationsClick?.(); }}
                style={{
                  width: "100%",
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  padding: "10px 12px",
                  borderRadius: "var(--radius-sm)",
                  fontSize: "13px",
                  color: "var(--text)",
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  textAlign: "left",
                }}
              >
                <Bell size={15} aria-hidden="true" />
                Notificações
                {pendingApprovals > 0 && (
                  <span style={{ marginLeft: "auto", fontSize: "11px", color: "var(--accent)", fontWeight: 600 }}>
                    {pendingApprovals}
                  </span>
                )}
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => { setMoreMenuOpen(false); toggleTheme(); }}
                style={{
                  width: "100%",
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  padding: "10px 12px",
                  borderRadius: "var(--radius-sm)",
                  fontSize: "13px",
                  color: "var(--text)",
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  textAlign: "left",
                }}
              >
                {theme === "dark" ? <Sun size={15} aria-hidden="true" /> : <Moon size={15} aria-hidden="true" />}
                {theme === "dark" ? "Tema claro" : "Tema escuro"}
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => { setMoreMenuOpen(false); onOpenHelp?.(); }}
                style={{
                  width: "100%",
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  padding: "10px 12px",
                  borderRadius: "var(--radius-sm)",
                  fontSize: "13px",
                  color: "var(--text)",
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  textAlign: "left",
                }}
              >
                <span aria-hidden="true" style={{ fontSize: 14, fontWeight: 600 }}>?</span>
                Ajuda
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => { setMoreMenuOpen(false); void handleLogout(); }}
                style={{
                  width: "100%",
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  padding: "10px 12px",
                  borderRadius: "var(--radius-sm)",
                  fontSize: "13px",
                  color: "var(--error)",
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  textAlign: "left",
                }}
              >
                <LogOut size={15} aria-hidden="true" />
                Sair
              </button>
            </div>
          )}
        </div>
      ) : (
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

        {/* + Novo (menu de criação rápida) */}
        <div style={{ position: "relative" }}>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setNewMenuOpen((o) => !o);
            }}
            aria-haspopup="menu"
            aria-expanded={newMenuOpen}
            aria-label="Criar novo"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              padding: "6px 12px",
              borderRadius: "var(--radius-sm)",
              border: "1px solid var(--border)",
              background: "var(--bg-card)",
              color: "var(--text)",
              fontSize: "13px",
              fontWeight: 500,
              cursor: "pointer",
              transition: "background var(--transition), border-color var(--transition), color var(--transition)",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = "var(--accent)";
              e.currentTarget.style.color = "var(--accent)";
              e.currentTarget.style.background = "var(--accent-subtle)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = "var(--border)";
              e.currentTarget.style.color = "var(--text)";
              e.currentTarget.style.background = "var(--bg-card)";
            }}
          >
            <span aria-hidden="true" style={{ fontSize: 16, lineHeight: 1 }}>+</span>
            Novo
            <ChevronDown size={14} aria-hidden="true" />
          </button>

          {newMenuOpen && (
            <div
              role="menu"
              aria-label="Criar novo"
              style={{
                position: "absolute",
                top: "calc(100% + 6px)",
                right: 0,
                zIndex: 20,
                minWidth: 220,
                padding: "6px",
                background: "var(--bg-elevated)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius)",
                boxShadow: "var(--shadow-md, 0 4px 16px rgba(0,0,0,0.2))",
              }}
            >
              <Link
                role="menuitem"
                href="/agents/new"
                onClick={() => setNewMenuOpen(false)}
                style={{
                  display: "block",
                  padding: "8px 12px",
                  borderRadius: "var(--radius-sm)",
                  fontSize: "13px",
                  color: "var(--text)",
                  textDecoration: "none",
                  background: "transparent",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = "var(--bg-hover)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "transparent";
                }}
              >
                Agente
              </Link>
              <button
                type="button"
                role="menuitem"
                onClick={handleCreatePipeline}
                style={{
                  width: "100%",
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  padding: "8px 12px",
                  borderRadius: "var(--radius-sm)",
                  fontSize: "13px",
                  color: "var(--text)",
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  textAlign: "left",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = "var(--bg-hover)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "transparent";
                }}
              >
                Pipeline
              </button>
              <Link
                role="menuitem"
                href="/knowledge?new=1"
                onClick={() => setNewMenuOpen(false)}
                style={{
                  display: "block",
                  padding: "8px 12px",
                  borderRadius: "var(--radius-sm)",
                  fontSize: "13px",
                  color: "var(--text)",
                  textDecoration: "none",
                  background: "transparent",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = "var(--bg-hover)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "transparent";
                }}
              >
                Base de conhecimento
              </Link>
            </div>
          )}
        </div>

        {/* Ajuda de atalhos (?) */}
        <button
          onClick={onOpenHelp}
          aria-label="Atalhos de teclado"
          title="Atalhos de teclado (?)"
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
            fontSize: "14px",
            fontWeight: 600,
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
          ?
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
      )}
    </header>
  );
}
