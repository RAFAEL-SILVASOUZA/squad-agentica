"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";

/**
 * Breadcrumb (Task 5).
 * Trilha de navegação: "Pipelines / Nome". Cada item é um Link; o último é a
 * página atual (não é link, `aria-current="page"`).
 */

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

export interface BreadcrumbProps {
  items: BreadcrumbItem[];
}

export function Breadcrumb({ items }: BreadcrumbProps) {
  const last = items.length - 1;

  return (
    <nav
      aria-label="Você está em"
      style={{
        display: "flex",
        alignItems: "center",
        flexWrap: "wrap",
        gap: "6px",
        fontSize: "12px",
        color: "var(--text-muted)",
      }}
    >
      {items.map((item, index) => {
        const isLast = index === last;

        return (
          <span key={item.label} style={{ display: "flex", alignItems: "center" }}>
            {index > 0 && (
              <ChevronRight size={14} aria-hidden="true" style={{ margin: "0 2px" }} />
            )}
            {isLast ? (
              <span aria-current="page" style={{ color: "var(--text)", fontWeight: 500 }}>
                {item.label}
              </span>
            ) : (
              <Link
                href={item.href ?? "#"}
                style={{
                  color: "var(--text-muted)",
                  textDecoration: "none",
                }}
              >
                {item.label}
              </Link>
            )}
          </span>
        );
      })}
    </nav>
  );
}
