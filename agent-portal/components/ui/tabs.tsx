"use client";

import * as React from "react";

/**
 * Tabs (design system §2.15).
 * Container com border-bottom; tab ativa com accent.
 */
export interface TabItem {
  id: string;
  label: string;
}

export interface TabsProps {
  tabs: TabItem[];
  activeTab: string;
  onTabChange: (id: string) => void;
  /**
   * Liga abas e painel (a11y): aba = `<prefix>-tab-<id>`, com
   * aria-controls = `<prefix>-panel` (o painel usa esse id e
   * aria-labelledby apontando para a aba ativa).
   */
  idPrefix?: string;
}

export function Tabs({ tabs, activeTab, onTabChange, idPrefix }: TabsProps) {
  return (
    <div
      role="tablist"
      style={{
        display: "flex",
        gap: "4px",
        borderBottom: "1px solid var(--border)",
      }}
    >
      {tabs.map((tab) => {
        const isActive = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            role="tab"
            id={idPrefix ? `${idPrefix}-tab-${tab.id}` : undefined}
            aria-controls={idPrefix ? `${idPrefix}-panel` : undefined}
            aria-selected={isActive}
            onClick={() => onTabChange(tab.id)}
            style={{
              padding: "8px 14px",
              fontSize: "13px",
              fontWeight: isActive ? 500 : 400,
              color: isActive ? "var(--accent)" : "var(--text-secondary)",
              background: "none",
              border: "none",
              borderBottom: isActive
                ? "2px solid var(--accent)"
                : "2px solid transparent",
              cursor: "pointer",
              transition: "color var(--transition), border-color var(--transition)",
              marginBottom: -1,
            }}
            onMouseEnter={(e) => {
              if (!isActive) e.currentTarget.style.color = "var(--text)";
            }}
            onMouseLeave={(e) => {
              if (!isActive) e.currentTarget.style.color = "var(--text-secondary)";
            }}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
