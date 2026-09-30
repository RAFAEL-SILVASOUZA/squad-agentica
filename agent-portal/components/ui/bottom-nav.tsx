"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Home, GitBranch, CheckCircle2, MoreHorizontal } from "lucide-react";

/**
 * Barra de navegação inferior (spec §2 Mobile).
 * Visível só abaixo de 768px. 4 itens: Início, Pipelines, Aprovações e Mais.
 * Cada item tem pelo menos 44px de altura. O item ativo leva aria-current="page".
 */

export interface BottomNavProps {
  pendingApprovals?: number;
  onOpenSidebar: () => void;
}

interface NavItemProps {
  icon: React.ReactNode;
  label: string;
  href?: string;
  onClick?: () => void;
  active: boolean;
  badge?: number;
}

function NavItem({ icon, label, href, onClick, active, badge }: NavItemProps) {
  const style: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: "2px",
    minHeight: "44px",
    width: "100%",
    border: "none",
    background: "transparent",
    color: active ? "var(--accent)" : "var(--text-muted)",
    cursor: "pointer",
    textDecoration: "none",
    position: "relative",
    padding: "4px 0",
  };

  const content = (
    <>
      <span style={{ position: "relative", display: "flex", alignItems: "center", justifyContent: "center" }}>
        {icon}
        {badge != null && badge > 0 && (
          <span
            aria-hidden="true"
            style={{
              position: "absolute",
              top: -4,
              right: -8,
              minWidth: 14,
              height: 14,
              borderRadius: "50%",
              background: "var(--accent)",
              color: "#fff",
              fontSize: "9px",
              fontWeight: 700,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              padding: "0 3px",
            }}
          >
            {badge > 9 ? "9+" : badge}
          </span>
        )}
      </span>
      <span style={{ fontSize: "10px", fontWeight: active ? 600 : 400 }}>{label}</span>
    </>
  );

  if (href) {
    return (
      <Link href={href} style={style} aria-current={active ? "page" : undefined} aria-label={label}>
        {content}
      </Link>
    );
  }

  return (
    <button type="button" style={style} onClick={onClick} aria-label={label} aria-current={active ? "page" : undefined}>
      {content}
    </button>
  );
}

export function BottomNav({ pendingApprovals = 0, onOpenSidebar }: BottomNavProps) {
  const pathname = usePathname();

  const isHome = pathname === "/";
  const isPipelines = pathname.startsWith("/pipelines");
  const isApprovals = pathname.startsWith("/approvals");

  return (
    <nav
      aria-label="Navegação inferior"
      style={{
        display: "flex",
        alignItems: "stretch",
        justifyContent: "space-around",
        height: "56px",
        background: "var(--bg-elevated)",
        borderTop: "1px solid var(--border)",
        paddingBottom: "env(safe-area-inset-bottom, 0px)",
        position: "fixed",
        bottom: 0,
        left: 0,
        right: 0,
        zIndex: 100,
      }}
    >
      <NavItem
        icon={<Home size={20} aria-hidden="true" />}
        label="Início"
        href="/"
        active={isHome}
      />
      <NavItem
        icon={<GitBranch size={20} aria-hidden="true" />}
        label="Pipelines"
        href="/pipelines"
        active={isPipelines}
      />
      <NavItem
        icon={<CheckCircle2 size={20} aria-hidden="true" />}
        label="Aprovações"
        href="/approvals"
        active={isApprovals}
        badge={pendingApprovals}
      />
      <NavItem
        icon={<MoreHorizontal size={20} aria-hidden="true" />}
        label="Mais"
        onClick={onOpenSidebar}
        active={false}
      />
    </nav>
  );
}
