import type { BadgeStatus } from "@/components/ui/badge";
import type { PipelineRun } from "@/lib/types";

/** Rótulos e badges de status compartilhados pelas peças do monitor. */

export type NodeStatus = "pending" | "running" | "completed" | "failed" | "waiting_approval";

export const NODE_STATUS_BADGE: Record<NodeStatus, BadgeStatus> = {
  pending: "pending",
  running: "running",
  completed: "completed",
  failed: "failed",
  waiting_approval: "warning",
};

export const NODE_STATUS_LABEL: Record<NodeStatus, string> = {
  pending: "Pendente",
  running: "Executando",
  completed: "Concluído",
  failed: "Falhou",
  waiting_approval: "Aguardando aprovação",
};

export const RUN_STATUS_BADGE: Record<PipelineRun["status"], BadgeStatus> = {
  running: "running",
  paused: "paused",
  completed: "completed",
  failed: "failed",
  cancelled: "cancelled",
};

export const RUN_STATUS_LABEL: Record<PipelineRun["status"], string> = {
  running: "Executando",
  paused: "Pausado",
  completed: "Concluído",
  failed: "Falhou",
  cancelled: "Cancelado",
};
