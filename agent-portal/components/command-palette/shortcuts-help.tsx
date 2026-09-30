"use client";

import * as React from "react";

export interface ShortcutsHelpProps {
  open: boolean;
  onClose: () => void;
}

const SHORTCUTS: Array<{ keys: string; description: string }> = [
  { keys: "Ctrl / ⌘ + K", description: "Abrir a paleta de comandos" },
  { keys: "/", description: "Abrir a paleta de comandos" },
  { keys: "?", description: "Mostrar esta ajuda" },
  { keys: "↑ / ↓", description: "Navegar pelos resultados" },
  { keys: "Enter", description: "Selecionar o item ativo" },
  { keys: "Esc", description: "Fechar" },
];

/**
 * Overlay de ajuda de atalhos de teclado. Abre com "?" (via useShortcuts no
 * shell) ou pelo botão "?" da topbar.
 */
export function ShortcutsHelp({ open, onClose }: ShortcutsHelpProps) {
  React.useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 10000,
        background: "rgba(0,0,0,0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label="Atalhos de teclado"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "100%",
          maxWidth: 420,
          background: "var(--bg-elevated)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          boxShadow: "0 8px 32px rgba(0,0,0,0.3)",
          padding: "20px 24px",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 16,
          }}
        >
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: "var(--text)" }}>
            Atalhos de teclado
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fechar"
            style={{
              border: "none",
              background: "transparent",
              color: "var(--text-secondary)",
              cursor: "pointer",
              fontSize: 18,
              lineHeight: 1,
            }}
          >
            ×
          </button>
        </div>
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 10 }}>
          {SHORTCUTS.map((s) => (
            <li
              key={s.keys}
              style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16 }}
            >
              <span style={{ color: "var(--text-secondary)", fontSize: 13 }}>{s.description}</span>
              <kbd
                style={{
                  fontFamily: "var(--font-mono, monospace)",
                  fontSize: 12,
                  padding: "2px 8px",
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--border)",
                  background: "var(--bg-card)",
                  color: "var(--text)",
                  whiteSpace: "nowrap",
                }}
              >
                {s.keys}
              </kbd>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
