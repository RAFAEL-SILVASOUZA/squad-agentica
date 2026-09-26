import type { Agent } from "@/lib/types";

/**
 * Busca no grid (client-side, contrato não expõe query param no
 * GET /api/agents) + filtro por tipo (server-side: GET /api/agents?type=,
 * contrato §9).
 */
export function filterAgentsBySearchAndType(
  agents: Agent[],
  search: string,
  typeFilter: string
): Agent[] {
  const query = search.trim().toLowerCase();
  return agents.filter((agent) => {
    if (typeFilter && agent.type !== typeFilter) return false;
    if (!query) return true;
    return (
      agent.name.toLowerCase().includes(query) ||
      agent.description.toLowerCase().includes(query) ||
      agent.type.toLowerCase().includes(query)
    );
  });
}
