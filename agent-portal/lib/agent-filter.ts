import type { Agent } from "@/lib/types";

/**
 * Busca no grid (client-side, contrato não expõe query param no
 * GET /api/agents) + filtro por tipo (server-side: GET /api/agents?type=,
 * contrato §9).
 * A busca ignora maiúsculas e acentos (normalização NFD).
 */
function normalize(s: string): string {
  return s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

export function filterAgentsBySearchAndType(
  agents: Agent[],
  search: string,
  typeFilter: string
): Agent[] {
  const query = normalize(search.trim());
  return agents.filter((agent) => {
    if (typeFilter && agent.type !== typeFilter) return false;
    if (!query) return true;
    return (
      normalize(agent.name).includes(query) ||
      normalize(agent.description).includes(query) ||
      normalize(agent.type).includes(query)
    );
  });
}
