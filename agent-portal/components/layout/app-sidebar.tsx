"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { LucideIcon } from "lucide-react";
import {
  LayoutGrid,
  Bot,
  CheckCircle2,
  BookOpen,
  Wrench,
  Server,
  FileText,
} from "lucide-react";

/**
 * Sidebar do shell (design system §2.12).
 * Navegação entre views via Link real.
 * Lista apenas as rotas do PLANO-FRONTEND.
 */

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  badge?: number;
}

interface NavSection {
  label: string;
  items: NavItem[];
}

const NAV_SECTIONS: NavSection[] = [
  {
    label: "Principal",
    items: [
      {
        href: "/",
        label: "Dashboard",
        icon: LayoutGrid,
      },
      {
        href: "/agents/new",
        label: "Novo Agente",
        icon: Bot,
      },
    ],
  },
  {
    label: "Pipelines",
    items: [
      {
        href: "/approvals",
        label: "Aprovações",
        icon: CheckCircle2,
      },
    ],
  },
  {
    label: "Biblioteca",
    items: [
      {
        href: "/skills",
        label: "Skills",
        icon: BookOpen,
      },
      {
        href: "/tools",
        label: "Tools Custom",
        icon: Wrench,
      },
      {
        href: "/mcp",
        label: "MCP Servers",
        icon: Server,
      },
      {
        href: "/knowledge",
        label: "Knowledge",
        icon: FileText,
      },
    ],
  },
];

export interface AppSidebarProps {
  pendingApprovals?: number;
}

export function AppSidebar({ pendingApprovals = 0 }: AppSidebarProps) {
  const pathname = usePathname();

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  return (
    <nav
      aria-label="Navegação principal"
      style={{
        background: "var(--bg-elevated)",
        borderRight: "1px solid var(--border)",
        padding: "16px 12px",
        display: "flex",
        flexDirection: "column",
        gap: "4px",
        width: 240,
        overflowY: "auto",
        height: "100%",
      }}
    >
      {NAV_SECTIONS.map((section) => (
        <div key={section.label} style={{ marginBottom: "8px" }}>
          <span
            style={{
              fontSize: "10px",
              fontWeight: 600,
              textTransform: "uppercase",
              letterSpacing: "1px",
              color: "var(--text-muted)",
              padding: "12px 12px 6px",
              display: "block",
            }}
          >
            {section.label}
          </span>
          {section.items.map((item) => {
            const active = isActive(item.href);
            const Icon = item.icon;
            const showBadge =
              item.href === "/approvals" && pendingApprovals > 0;

            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "10px",
                  padding: "8px 12px",
                  borderRadius: "var(--radius-sm)",
                  fontSize: "13px",
                  fontWeight: active ? 500 : 400,
                  color: active ? "var(--text)" : "var(--text-secondary)",
                  background: active ? "var(--bg-hover)" : "transparent",
                  transition: "background var(--transition), color var(--transition)",
                }}
              >
                <Icon
                  size={16}
                  aria-label={item.label}
                  style={{
                    color: active ? "var(--accent)" : "var(--text-muted)",
                    flexShrink: 0,
                  }}
                />
                <span style={{ flex: 1 }}>{item.label}</span>
                {showBadge && (
                  <span
                    aria-label={`${pendingApprovals} aprovações pendentes`}
                    style={{
                      fontSize: "10px",
                      fontWeight: 600,
                      background: "var(--accent)",
                      color: "#fff",
                      borderRadius: "10px",
                      padding: "1px 6px",
                      minWidth: 18,
                      textAlign: "center",
                    }}
                  >
                    {pendingApprovals}
                  </span>
                )}
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
