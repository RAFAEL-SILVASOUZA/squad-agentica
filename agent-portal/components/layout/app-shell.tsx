"use client";

import * as React from "react";
import { AppSidebar } from "./app-sidebar";
import { AppTopbar } from "./app-topbar";
import { useShortcuts } from "@/components/command-palette/use-shortcuts";
import { CommandPalette } from "@/components/command-palette/command-palette";
import { ShortcutsHelp } from "@/components/command-palette/shortcuts-help";

/**
 * App Shell (design system §3.1).
 * Grid: topbar (56px) + sidebar (240px) + main.
 * Responsivo: sidebar recolhível em < 900px.
 */
export interface AppShellProps {
  children: React.ReactNode;
  pendingApprovals?: number;
  onNotificationsClick?: () => void;
}

export function AppShell({
  children,
  pendingApprovals = 0,
  onNotificationsClick,
}: AppShellProps) {
  const [sidebarOpen, setSidebarOpen] = React.useState(true);
  const [isMobile, setIsMobile] = React.useState(false);
  const [paletteOpen, setPaletteOpen] = React.useState(false);
  const [helpOpen, setHelpOpen] = React.useState(false);

  useShortcuts({
    onPalette: () => setPaletteOpen(true),
    onHelp: () => setHelpOpen(true),
  });

  React.useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 900);
    checkMobile();
    window.addEventListener("resize", checkMobile);
    return () => window.removeEventListener("resize", checkMobile);
  }, []);

  React.useEffect(() => {
    if (isMobile) setSidebarOpen(false);
    else setSidebarOpen(true);
  }, [isMobile]);

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: sidebarOpen && !isMobile ? "240px 1fr" : "1fr",
        gridTemplateRows: "56px 1fr",
        height: "100vh",
        overflow: "hidden",
      }}
    >
      {/* Topbar spans full width */}
      <div style={{ gridColumn: "1 / -1" }}>
        <AppTopbar
          pendingApprovals={pendingApprovals}
          onNotificationsClick={onNotificationsClick}
          onOpenHelp={() => setHelpOpen(true)}
        />
      </div>

      {/* Sidebar */}
      {sidebarOpen && !isMobile && (
        <div style={{ overflow: "hidden" }}>
          <AppSidebar pendingApprovals={pendingApprovals} />
        </div>
      )}

      {/* Mobile sidebar overlay */}
      {isMobile && sidebarOpen && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 9998,
            background: "rgba(0,0,0,0.5)",
          }}
          onClick={() => setSidebarOpen(false)}
        />
      )}
      {isMobile && sidebarOpen && (
        <div
          style={{
            position: "fixed",
            top: 56,
            left: 0,
            bottom: 0,
            zIndex: 9999,
          }}
        >
          <AppSidebar pendingApprovals={pendingApprovals} />
        </div>
      )}

      {/* Main content */}
      <main
        style={{
          overflowY: "auto",
          // No celular o botão de menu (absoluto em 16,16) cobria o início do
          // conteúdo (ex.: botão Voltar): o conteúdo começa abaixo dele.
          padding: isMobile ? "64px 16px 24px" : "24px",
          position: "relative",
        }}
      >
        {/* Mobile hamburger */}
        {isMobile && (
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            aria-label={sidebarOpen ? "Fechar menu" : "Abrir menu"}
            style={{
              position: "absolute",
              top: 16,
              left: 16,
              width: 36,
              height: 36,
              borderRadius: "var(--radius-sm)",
              border: "1px solid var(--border)",
              background: "var(--bg-card)",
              color: "var(--text)",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 1,
            }}
          >
            <span
              aria-hidden="true"
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 3,
              }}
            >
              <span
                style={{
                  width: 16,
                  height: 2,
                  background: "currentColor",
                  borderRadius: 1,
                }}
              />
              <span
                style={{
                  width: 16,
                  height: 2,
                  background: "currentColor",
                  borderRadius: 1,
                }}
              />
              <span
                style={{
                  width: 16,
                  height: 2,
                  background: "currentColor",
                  borderRadius: 1,
                }}
              />
            </span>
          </button>
        )}
        {children}
      </main>

      {/* Paleta de comandos (Ctrl/⌘K ou "/") e ajuda de atalhos ("?") */}
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
      <ShortcutsHelp open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  );
}
