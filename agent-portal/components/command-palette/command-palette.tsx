"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { usePaletteData } from "./use-palette-data";
import { matches } from "./utils";
import { useCreatePipelineAndNavigate } from "@/lib/create-pipeline";

export interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
}

type ActionKind = "new-agent" | "new-pipeline" | "new-base";

interface Row {
  key: string;
  label: string;
  kind: "action" | "item";
  action?: ActionKind;
  href?: string;
}

const FIXED_ACTIONS: Row[] = [
  { key: "act-new-agent", label: "Novo agente", kind: "action", action: "new-agent" },
  { key: "act-new-pipeline", label: "Nova pipeline", kind: "action", action: "new-pipeline" },
  { key: "act-new-base", label: "Nova base", kind: "action", action: "new-base" },
];

/**
 * Paleta de comandos (design system §2.14). Abre com Ctrl/⌘K ou "/" (via
 * useShortcuts no shell). Busca com debounce de 200 ms, filtrada no cliente
 * por nome (sem distinguir maiúsculas/acentos), agrupada por tipo, com ações
 * fixas de criação. Setas navegam, Enter seleciona, Esc fecha.
 */
export function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const router = useRouter();
  const createPipelineAndNavigate = useCreatePipelineAndNavigate();
  const { groups, loading } = usePaletteData(open);
  const [query, setQuery] = React.useState("");
  const [debouncedQuery, setDebouncedQuery] = React.useState("");
  const [activeIndex, setActiveIndex] = React.useState(0);
  const inputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    if (open) {
      setQuery("");
      setDebouncedQuery("");
      setActiveIndex(0);
      inputRef.current?.focus();
    }
  }, [open]);

  React.useEffect(() => {
    const t = setTimeout(() => setDebouncedQuery(query), 200);
    return () => clearTimeout(t);
  }, [query]);

  const filteredGroups = React.useMemo(
    () =>
      groups
        .map((g) => ({ ...g, items: g.items.filter((it) => matches(debouncedQuery, it.name)) }))
        .filter((g) => g.items.length > 0),
    [groups, debouncedQuery]
  );

  const rows: Row[] = React.useMemo(() => {
    const itemRows: Row[] = filteredGroups.flatMap((g) =>
      g.items.map((it) => ({
        key: `${g.type}-${it.id}`,
        label: it.name,
        kind: "item" as const,
        href: it.href,
      }))
    );
    return [...FIXED_ACTIONS, ...itemRows];
  }, [filteredGroups]);

  const hasItems = rows.some((r) => r.kind === "item");
  const noResults = debouncedQuery.trim() !== "" && !hasItems;

  React.useEffect(() => {
    if (activeIndex >= rows.length) setActiveIndex(Math.max(0, rows.length - 1));
  }, [rows.length, activeIndex]);

  const selectRow = (row: Row) => {
    if (row.action === "new-agent") router.push("/agents/new");
    else if (row.action === "new-pipeline") void createPipelineAndNavigate();
    else if (row.action === "new-base") router.push("/knowledge?new=1");
    else if (row.href) router.push(row.href);
    onClose();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, rows.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const row = rows[activeIndex];
      if (row) selectRow(row);
    } else if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    }
  };

  if (!open) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 10000,
        background: "rgba(0,0,0,0.5)",
        display: "flex",
        justifyContent: "center",
        alignItems: "flex-start",
        paddingTop: 120,
      }}
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label="Buscar"
        aria-modal="true"
        onKeyDown={handleKeyDown}
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "100%",
          maxWidth: 640,
          background: "var(--bg-elevated)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          boxShadow: "0 8px 32px rgba(0,0,0,0.3)",
          overflow: "hidden",
        }}
      >
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Buscar agentes, pipelines, skills…"
          aria-label="Buscar"
          style={{
            width: "100%",
            boxSizing: "border-box",
            padding: "12px 16px",
            border: "none",
            borderBottom: "1px solid var(--border)",
            background: "transparent",
            color: "var(--text)",
            fontSize: 15,
            outline: "none",
          }}
        />
        <div style={{ maxHeight: 400, overflowY: "auto", padding: 8 }}>
          {loading ? (
            <div style={{ padding: "12px 16px", color: "var(--text-secondary)", fontSize: 13 }}>
              Carregando…
            </div>
          ) : (
            <>
              {rows.map((row, i) => (
                <button
                  key={row.key}
                  type="button"
                  onClick={() => selectRow(row)}
                  onMouseEnter={() => setActiveIndex(i)}
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    padding: "8px 12px",
                    borderRadius: "var(--radius-sm)",
                    border: "none",
                    background: i === activeIndex ? "var(--bg-hover)" : "transparent",
                    color: "var(--text)",
                    fontSize: 14,
                    cursor: "pointer",
                  }}
                >
                  {row.label}
                </button>
              ))}
              {noResults && (
                <div style={{ padding: "12px 16px", color: "var(--text-secondary)", fontSize: 13 }}>
                  Nada encontrado para &apos;{debouncedQuery}&apos;
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
