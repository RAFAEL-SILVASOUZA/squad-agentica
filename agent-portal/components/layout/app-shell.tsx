"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
import { AppSidebar } from "./app-sidebar";
import { AppTopbar } from "./app-topbar";
import { BottomNav } from "@/components/ui/bottom-nav";
import { useShortcuts } from "@/components/command-palette/use-shortcuts";
import { CommandPalette } from "@/components/command-palette/command-palette";
import { ShortcutsHelp } from "@/components/command-palette/shortcuts-help";

/**
 * App Shell (design system §3.1).
 * Grid: topbar (56px) + sidebar (240px) + main.
 * Responsivo: sidebar recolhível em < 768px, bottom nav visível.
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
  const pathname = usePathname();

  // Título da tela para a topbar mobile (spec: "logo, o título da tela e ⋯").
  const pageTitle = React.useMemo(() => {
    if (pathname === "/") return "Início";
    if (pathname.startsWith("/pipelines")) return "Pipelines";
    if (pathname.startsWith("/approvals")) return "Aprovações";
    if (pathname.startsWith("/agents")) return "Agentes";
    if (pathname.startsWith("/knowledge")) return "Knowledge";
    if (pathname.startsWith("/integrations")) return "Integrações";
    if (pathname.startsWith("/library")) return "Biblioteca";
    return "Agent Portal";
  }, [pathname]);

  useShortcuts({
    onPalette: () => setPaletteOpen(true),
    onHelp: () => setHelpOpen(true),
  });

  React.useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth < 768);
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
        height: "100dvh",
        overflow: "hidden",
      }}
    >
      {/* Topbar spans full width */}
      <div style={{ gridColumn: "1 / -1" }}>
        <AppTopbar
          pendingApprovals={pendingApprovals}
          onNotificationsClick={onNotificationsClick}
          onOpenHelp={() => setHelpOpen(true)}
          isMobile={isMobile}
          title={pageTitle}
        />
      </div>

      {/* Sidebar (desktop) */}
      {sidebarOpen && !isMobile && (
        <div style={{ overflow: "hidden" }}>
          <AppSidebar pendingApprovals={pendingApprovals} />
        </div>
      )}

      {/* Mobile sidebar overlay (aberto pelo "Mais" da bottom nav) */}
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
          scrollbarGutter: "stable",
          padding: isMobile ? "16px 16px 72px" : "24px",
          position: "relative",
        }}
      >
        {children}
      </main>

      {/* Bottom nav (mobile) */}
      {isMobile && (
        <BottomNav
          pendingApprovals={pendingApprovals}
          onOpenSidebar={() => setSidebarOpen(true)}
        />
      )}

      {/* Paleta de comandos (Ctrl/⌘K ou "/") e ajuda de atalhos ("?") */}
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
      <ShortcutsHelp open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  );
}
