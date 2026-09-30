"use client";

import * as React from "react";
import { api } from "@/lib/api";

export type PaletteItem = { id: string; name: string; type: string; href: string };
export type PaletteGroup = { type: string; label: string; items: PaletteItem[] };

type SourceKey = "agents" | "pipelines" | "knowledge" | "skills" | "tools" | "mcp-servers";

const GROUP_LABELS: Record<SourceKey, string> = {
  agents: "Agentes",
  pipelines: "Pipelines",
  knowledge: "Base de conhecimento",
  skills: "Skills",
  tools: "Tools",
  "mcp-servers": "MCP Servers",
};

interface Source {
  type: SourceKey;
  path: string;
  href: (id: string) => string;
}

const SOURCES: Source[] = [
  { type: "agents", path: "/api/agents", href: (id) => `/agents/${id}` },
  { type: "pipelines", path: "/api/pipelines", href: (id) => `/pipelines/${id}` },
  { type: "knowledge", path: "/api/knowledge", href: () => "/knowledge" },
  { type: "skills", path: "/api/skills", href: () => "/skills" },
  { type: "tools", path: "/api/tools", href: () => "/tools" },
  { type: "mcp-servers", path: "/api/mcp-servers", href: () => "/mcp" },
];

/**
 * Carrega as listas de navegação da paleta de comandos.
 *
 * Quando `open` vira true, busca as 6 listas em paralelo (Promise.allSettled:
 * uma falha não derruba as demais) e agrupa os itens por tipo. Recarrega a
 * cada transição de `open` para true (depende de `open`, não de render).
 */
export function usePaletteData(open: boolean): { groups: PaletteGroup[]; loading: boolean } {
  const [groups, setGroups] = React.useState<PaletteGroup[]>([]);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (!open) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);

    void (async () => {
      const results = await Promise.allSettled(
        SOURCES.map((s) => api.list<{ id: string; name: string }>(s.path, { limit: 50 }))
      );

      if (cancelled) return;

      const nextGroups: PaletteGroup[] = [];
      results.forEach((result, idx) => {
        if (result.status !== "fulfilled") return;
        const source = SOURCES[idx];
        const items: PaletteItem[] = result.value.items.map((item) => ({
          id: item.id,
          name: item.name,
          type: source.type,
          href: source.href(item.id),
        }));
        if (items.length > 0) {
          nextGroups.push({ type: source.type, label: GROUP_LABELS[source.type], items });
        }
      });

      setGroups(nextGroups);
      setLoading(false);
    })();

    return () => {
      cancelled = true;
    };
  }, [open]);

  return { groups, loading };
}
