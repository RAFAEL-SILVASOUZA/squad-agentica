/**
 * Helpers de CRUD de agentes (consome lib/api.ts).
 *
 * Endpoints (nó be-agents, contrato §9):
 * - GET    /api/agents/{id}
 * - PUT    /api/agents/{id}   (partial update)
 * - DELETE /api/agents/{id}
 *
 * A listagem (GET /api/agents) é usada pelo dashboard; aqui expomos os
 * helpers de detalhe/edição usados pelas telas de fe-agents.
 */

import { api } from "./api";
import type { Agent, PaginatedResponse } from "./types";

export interface AgentUpdatePayload {
  name?: string;
  type?: string;
  description?: string;
  prompt?: string;
  strategy?: string;
  skills?: Agent["skills"];
  tools?: Agent["tools"];
  mcpServers?: Agent["mcpServers"];
  knowledge?: Agent["knowledge"];
  integrations?: Agent["integrations"];
  inputs?: Agent["inputs"];
  outputs?: Agent["outputs"];
  actions?: Agent["actions"];
  model?: string;
  maxIterations?: number;
  timeout?: number;
  shellAccess?: boolean;
}

/** Obtém um agente por id. Lança ApiError(404) se não existir. */
export function getAgent(id: string): Promise<Agent> {
  return api.get<Agent>(`/api/agents/${id}`);
}

/** Atualiza um agente (partial update). */
export function updateAgent(
  id: string,
  payload: AgentUpdatePayload
): Promise<Agent> {
  return api.put<Agent>(`/api/agents/${id}`, payload);
}

/** Remove um agente. */
export function deleteAgent(id: string): Promise<void> {
  return api.delete<void>(`/api/agents/${id}`);
}

/** Lista agentes (usado pelos seletores de mochila e pelo dashboard). */
export function listAgents(opts?: {
  page?: number;
  limit?: number;
  type?: string;
}): Promise<PaginatedResponse<Agent>> {
  return api.list<Agent>("/api/agents", {
    page: opts?.page,
    limit: opts?.limit,
    query: { type: opts?.type },
  });
}
