"use client";

import * as React from "react";
import { MoreVertical, Search, X } from "lucide-react";

/**
 * DataTable (design system §2.9, Task 10).
 *
 * - Busca no cliente (ignora acentos, case-insensitive).
 * - Filtros por select.
 * - Ordenação por coluna (aria-sort).
 * - Menu ⋮ por linha (role="menu").
 * - Abaixo de 768px: cada linha vira card de duas linhas.
 */

export interface DataTableColumn<T> {
  key: string;
  header: string;
  render?: (row: T) => React.ReactNode;
  sortable?: boolean;
  width?: string;
}

export interface DataTableFilter {
  key: string;
  label: string;
  options: { value: string; label: string }[];
}

export interface DataTableRowMenuItem {
  label: string;
  action: string;
  danger?: boolean;
}

export interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  searchPlaceholder?: string;
  filters?: DataTableFilter[];
  onRowMenu?: (row: T, action: string) => void;
  rowMenuItems?: DataTableRowMenuItem[];
  emptyMessage?: string;
}

/** Remove acentos para busca case/accent-insensitive. */
function normalize(s: string): string {
  return s
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

type SortDir = "asc" | "desc" | null;

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  searchPlaceholder,
  filters,
  onRowMenu,
  rowMenuItems,
  emptyMessage = "Nenhum item encontrado",
}: DataTableProps<T>) {
  const [search, setSearch] = React.useState("");
  const [filterValues, setFilterValues] = React.useState<Record<string, string>>({});
  const [sortKey, setSortKey] = React.useState<string | null>(null);
  const [sortDir, setSortDir] = React.useState<SortDir>(null);
  const [openMenuId, setOpenMenuId] = React.useState<string | null>(null);
  const [isMobile, setIsMobile] = React.useState(false);

  React.useEffect(() => {
    const mql = window.matchMedia("(max-width: 767px)");
    setIsMobile(mql.matches);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, []);

  // Fecha menu ao clicar fora.
  React.useEffect(() => {
    if (!openMenuId) return;
    const handler = () => setOpenMenuId(null);
    document.addEventListener("click", handler);
    return () => document.removeEventListener("click", handler);
  }, [openMenuId]);

  const filtered = React.useMemo(() => {
    let result = rows;

    // Busca
    if (search.trim()) {
      const q = normalize(search.trim());
      result = result.filter((row) =>
        columns.some((col) => {
          const val = (row as Record<string, unknown>)[col.key];
          return typeof val === "string" && normalize(val).includes(q);
        })
      );
    }

    // Filtros
    for (const filter of filters ?? []) {
      const val = filterValues[filter.key];
      if (val) {
        result = result.filter(
          (row) => String((row as Record<string, unknown>)[filter.key]) === val
        );
      }
    }

    // Ordenação
    if (sortKey && sortDir) {
      const col = columns.find((c) => c.key === sortKey);
      if (col) {
        result = [...result].sort((a, b) => {
          const av = (a as Record<string, unknown>)[sortKey];
          const bv = (b as Record<string, unknown>)[sortKey];
          if (typeof av === "number" && typeof bv === "number") {
            return sortDir === "asc" ? av - bv : bv - av;
          }
          const as = String(av ?? "");
          const bs = String(bv ?? "");
          return sortDir === "asc" ? as.localeCompare(bs) : bs.localeCompare(as);
        });
      }
    }

    return result;
  }, [rows, search, filterValues, sortKey, sortDir, columns, filters]);

  const toggleSort = (key: string) => {
    if (sortKey !== key) {
      setSortKey(key);
      setSortDir("asc");
    } else if (sortDir === "asc") {
      setSortDir("desc");
    } else {
      setSortKey(null);
      setSortDir(null);
    }
  };

  const handleMenuAction = (row: T, action: string) => {
    setOpenMenuId(null);
    onRowMenu?.(row, action);
  };

  const cellContent = (row: T, col: DataTableColumn<T>) => {
    if (col.render) return col.render(row);
    const val = (row as Record<string, unknown>)[col.key];
    return String(val ?? "");
  };

  // ── Mobile: cards ──────────────────────────────────────────────────────────

  if (isMobile) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        {searchPlaceholder && (
          <div style={{ position: "relative" }}>
            <Search
              size={14}
              aria-hidden="true"
              style={{ position: "absolute", left: "10px", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }}
            />
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={searchPlaceholder}
              aria-label={searchPlaceholder}
              style={{
                width: "100%",
                padding: "10px 14px 10px 32px",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border)",
                background: "var(--bg-elevated)",
                color: "var(--text)",
                fontSize: "13px",
                outline: "none",
              }}
            />
          </div>
        )}
        {filters?.map((f) => (
          <select
            key={f.key}
            value={filterValues[f.key] ?? ""}
            onChange={(e) => setFilterValues((prev) => ({ ...prev, [f.key]: e.target.value }))}
            aria-label={f.label}
            style={{
              padding: "10px 14px",
              borderRadius: "var(--radius-sm)",
              border: "1px solid var(--border)",
              background: "var(--bg-elevated)",
              color: "var(--text)",
              fontSize: "13px",
              width: "100%",
            }}
          >
            <option value="">{f.label}: todos</option>
            {f.options.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        ))}
        {filtered.length === 0 ? (
          <div style={{ padding: "24px", textAlign: "center", color: "var(--text-muted)", fontSize: "13px" }}>
            {emptyMessage}
          </div>
        ) : (
          filtered.map((row) => (
            <div
              key={rowKey(row)}
              style={{
                background: "var(--bg-card)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius)",
                padding: "12px 14px",
                display: "flex",
                flexDirection: "column",
                gap: "6px",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "13px", fontWeight: 600, color: "var(--text)" }}>
                  {cellContent(row, columns[0])}
                </span>
                {onRowMenu && rowMenuItems && (
                  <div style={{ position: "relative" }}>
                    <button
                      type="button"
                      aria-label="Ações"
                      onClick={(e) => {
                        e.stopPropagation();
                        setOpenMenuId(openMenuId === rowKey(row) ? null : rowKey(row));
                      }}
                      style={{
                        background: "none",
                        border: "none",
                        cursor: "pointer",
                        color: "var(--text-muted)",
                        padding: "4px",
                        display: "flex",
                        alignItems: "center",
                      }}
                    >
                      <MoreVertical size={16} aria-hidden="true" />
                    </button>
                    {openMenuId === rowKey(row) && (
                      <div
                        role="menu"
                        style={{
                          position: "absolute",
                          right: 0,
                          top: "100%",
                          background: "var(--bg-elevated)",
                          border: "1px solid var(--border)",
                          borderRadius: "var(--radius-sm)",
                          boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
                          zIndex: 10,
                          minWidth: "140px",
                        }}
                      >
                        {rowMenuItems.map((item) => (
                          <button
                            key={item.action}
                            type="button"
                            role="menuitem"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleMenuAction(row, item.action);
                            }}
                            style={{
                              display: "block",
                              width: "100%",
                              padding: "8px 12px",
                              fontSize: "12px",
                              textAlign: "left",
                              background: "none",
                              border: "none",
                              cursor: "pointer",
                              color: item.danger ? "var(--error)" : "var(--text)",
                            }}
                          >
                            {item.label}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
              {columns.slice(1).map((col) => (
                <div key={col.key} style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
                  {cellContent(row, col)}
                </div>
              ))}
            </div>
          ))
        )}
      </div>
    );
  }

  // ── Desktop: tabela ────────────────────────────────────────────────────────

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
      {/* Toolbar: busca + filtros */}
      {(searchPlaceholder || filters?.length) && (
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
          {searchPlaceholder && (
            <div style={{ position: "relative", flex: "1 1 200px", maxWidth: "320px" }}>
              <Search
                size={14}
                aria-hidden="true"
                style={{ position: "absolute", left: "10px", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }}
              />
              <input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={searchPlaceholder}
                aria-label={searchPlaceholder}
                style={{
                  width: "100%",
                  padding: "8px 12px 8px 32px",
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--border)",
                  background: "var(--bg-elevated)",
                  color: "var(--text)",
                  fontSize: "13px",
                  outline: "none",
                }}
              />
            </div>
          )}
          {filters?.map((f) => (
            <select
              key={f.key}
              value={filterValues[f.key] ?? ""}
              onChange={(e) => setFilterValues((prev) => ({ ...prev, [f.key]: e.target.value }))}
              aria-label={f.label}
              style={{
                padding: "8px 12px",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border)",
                background: "var(--bg-elevated)",
                color: "var(--text)",
                fontSize: "13px",
              }}
            >
              <option value="">{f.label}: todos</option>
              {f.options.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          ))}
        </div>
      )}

      {/* Tabela */}
      {filtered.length === 0 ? (
        <div style={{ padding: "24px", textAlign: "center", color: "var(--text-muted)", fontSize: "13px" }}>
          {emptyMessage}
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
            <thead>
              <tr>
                {columns.map((col) => (
                  <th
                    key={col.key}
                    aria-sort={
                      sortKey === col.key ? (sortDir === "asc" ? "ascending" : "descending") : undefined
                    }
                    style={{
                      textAlign: "left",
                      fontSize: "10px",
                      textTransform: "uppercase",
                      letterSpacing: "0.5px",
                      color: "var(--text-muted)",
                      padding: "8px",
                      borderBottom: "1px solid var(--border)",
                      width: col.width,
                    }}
                  >
                    {col.sortable ? (
                      <button
                        type="button"
                        onClick={() => toggleSort(col.key)}
                        style={{
                          background: "none",
                          border: "none",
                          cursor: "pointer",
                          color: "var(--text-muted)",
                          fontSize: "10px",
                          textTransform: "uppercase",
                          letterSpacing: "0.5px",
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "4px",
                          padding: 0,
                        }}
                      >
                        {col.header}
                        {sortKey === col.key && (
                          <span aria-hidden="true">{sortDir === "asc" ? "↑" : "↓"}</span>
                        )}
                      </button>
                    ) : (
                      col.header
                    )}
                  </th>
                ))}
                {onRowMenu && rowMenuItems && (
                  <th style={{ width: "40px" }} />
                )}
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => (
                <tr
                  key={rowKey(row)}
                  style={{ borderBottom: "1px solid var(--border-subtle)" }}
                >
                  {columns.map((col) => (
                    <td key={col.key} style={{ padding: "8px", color: "var(--text)" }}>
                      {cellContent(row, col)}
                    </td>
                  ))}
                  {onRowMenu && rowMenuItems && (
                    <td style={{ padding: "4px 8px", textAlign: "right" }}>
                      <div style={{ position: "relative", display: "inline-block" }}>
                        <button
                          type="button"
                          aria-label="Ações"
                          onClick={(e) => {
                            e.stopPropagation();
                            setOpenMenuId(openMenuId === rowKey(row) ? null : rowKey(row));
                          }}
                          style={{
                            background: "none",
                            border: "none",
                            cursor: "pointer",
                            color: "var(--text-muted)",
                            padding: "4px",
                            display: "flex",
                            alignItems: "center",
                          }}
                        >
                          <MoreVertical size={14} aria-hidden="true" />
                        </button>
                        {openMenuId === rowKey(row) && (
                          <div
                            role="menu"
                            style={{
                              position: "absolute",
                              right: 0,
                              top: "100%",
                              background: "var(--bg-elevated)",
                              border: "1px solid var(--border)",
                              borderRadius: "var(--radius-sm)",
                              boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
                              zIndex: 10,
                              minWidth: "140px",
                            }}
                          >
                            {rowMenuItems.map((item) => (
                              <button
                                key={item.action}
                                type="button"
                                role="menuitem"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleMenuAction(row, item.action);
                                }}
                                style={{
                                  display: "block",
                                  width: "100%",
                                  padding: "8px 12px",
                                  fontSize: "12px",
                                  textAlign: "left",
                                  background: "none",
                                  border: "none",
                                  cursor: "pointer",
                                  color: item.danger ? "var(--error)" : "var(--text)",
                                }}
                              >
                                {item.label}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
