import type { NodeStatus } from "./status";

export interface TimelineEvent {
  nodeId: string;
  status: string;
  at: string;
}

export interface TimelineCheckpoint {
  nodeId: string;
  timestamp: string;
  status: string;
}

export interface TimelineEntry {
  nodeId: string;
  startedAt?: string;
  endedAt?: string;
  durationMs?: number;
  status: NodeStatus;
}

/**
 * Monta a linha do tempo por nó a partir dos eventos WS e checkpoints.
 *
 * Regras:
 * - O início é o primeiro evento `running` do nó.
 * - O fim é o primeiro evento `completed` ou `failed` depois do início.
 * - Na ausência de eventos, os dados vêm dos checkpoints (só `endedAt` e `status`).
 * - Eventos têm prioridade sobre checkpoints para o mesmo nó.
 */
export function buildTimeline(
  events: TimelineEvent[],
  checkpoints: TimelineCheckpoint[]
): TimelineEntry[] {
  // Agrupa eventos por nó, preservando a ordem.
  const eventsByNode = new Map<string, TimelineEvent[]>();
  for (const ev of events) {
    const list = eventsByNode.get(ev.nodeId) ?? [];
    list.push(ev);
    eventsByNode.set(ev.nodeId, list);
  }

  // Agrupa checkpoints por nó (último checkpoint por nó).
  const cpByNode = new Map<string, TimelineCheckpoint>();
  for (const cp of checkpoints) {
    cpByNode.set(cp.nodeId, cp);
  }

  const entries: TimelineEntry[] = [];
  const seen = new Set<string>();

  // Nós com eventos têm prioridade.
  for (const [nodeId, nodeEvents] of eventsByNode) {
    seen.add(nodeId);
    let startedAt: string | undefined;
    let endedAt: string | undefined;
    let status: NodeStatus = "pending";

    for (const ev of nodeEvents) {
      if (ev.status === "running" && !startedAt) {
        startedAt = ev.at;
        status = "running";
      } else if ((ev.status === "completed" || ev.status === "failed") && startedAt && !endedAt) {
        endedAt = ev.at;
        status = ev.status as NodeStatus;
      } else if (ev.status === "waiting_approval" && !endedAt) {
        status = "waiting_approval";
      }
    }

    // Se não há startedAt mas há um status terminal, usa como endedAt.
    if (!startedAt && endedAt) {
      status = endedAt ? (status as NodeStatus) : "completed";
    }

    const durationMs =
      startedAt && endedAt ? new Date(endedAt).getTime() - new Date(startedAt).getTime() : undefined;

    entries.push({ nodeId, startedAt, endedAt, durationMs, status });
  }

  // Nós só com checkpoints.
  for (const [nodeId, cp] of cpByNode) {
    if (seen.has(nodeId)) continue;
    seen.add(nodeId);
    const status: NodeStatus =
      cp.status === "completed" ? "completed" : cp.status === "failed" ? "failed" : "pending";
    entries.push({
      nodeId,
      startedAt: undefined,
      endedAt: cp.timestamp,
      durationMs: undefined,
      status,
    });
  }

  return entries;
}
