/**
 * Tipos espelhando os schemas reais da API (spec §4 + GUIA-API-FRONTEND.md).
 * camelCase em toda a API (contrato §8).
 */

// ─── Agente (spec §4.1) ───────────────────────────────────────────────

export interface PortDef {
  name: string;
  type: string;
  required: boolean;
}

export type FlowAction = "follow" | "return" | "finalize";

export interface SkillRef {
  skillId: string;
  config: Record<string, unknown>;
}

export interface ToolRef {
  toolId: string;
  config: Record<string, unknown>;
}

export interface MCPServerRef {
  serverId: string;
  toolFilter?: string[];
}

export interface KnowledgeRef {
  source: "upload" | "vector-db" | "url" | "rivvn";
  reference: string;
}

export interface IntegrationRef {
  platform: "azure" | "github" | "gitlab" | "azure-devops" | "email" | "custom";
  config: Record<string, unknown>;
}

export interface Agent {
  id: string;
  ownerId: string;
  name: string;
  type: string;
  description: string;
  prompt: string;
  strategy: string;
  skills: SkillRef[];
  tools: ToolRef[];
  mcpServers: MCPServerRef[];
  knowledge: KnowledgeRef[];
  integrations: IntegrationRef[];
  inputs: PortDef[];
  outputs: PortDef[];
  actions: FlowAction[];
  model: string;
  maxIterations: number;
  timeout: number;
  shellAccess: boolean;
}

// ─── Pipeline (spec §4.2) ─────────────────────────────────────────────

export interface AgentSnapshot {
  agentId: string;
  version: number;
  name: string;
  description: string;
  prompt: string;
  strategy: string;
  skills: SkillRef[];
  tools: ToolRef[];
  mcpServers: MCPServerRef[];
  knowledge: KnowledgeRef[];
  integrations: IntegrationRef[];
  inputs: PortDef[];
  outputs: PortDef[];
  actions: FlowAction[];
  model: string;
  maxIterations: number;
  timeout: number;
  shellAccess: boolean;
}

export interface PipelineNode {
  id: string;
  agentId: string;
  position: { x: number; y: number };
  label?: string;
  agentSnapshot: AgentSnapshot;
}

export type EdgeType = "flow" | "data";

export interface DataMapping {
  sourceOutput: string;
  targetInput: string;
}

export interface EdgeCondition {
  field: "action";
  operator: "eq" | "neq" | "in" | "not_in";
  value: string | string[];
}

export type NotificationChannel = "in-app" | "email" | "teams" | "slack";

export interface PipelineEdge {
  id: string;
  type: EdgeType;
  source: string;
  target: string;
  condition?: EdgeCondition;
  label?: string;
  requiresApproval: boolean;
  approvalChannel?: NotificationChannel;
  approvalMessage?: string;
  dataMapping?: DataMapping;
}

export interface Pipeline {
  id: string;
  ownerId: string;
  name: string;
  description: string;
  status: "draft" | "running" | "paused" | "completed" | "failed";
  entryNodeId: string;
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  currentCheckpoint: string | null;
  startedAt: string | null;
  completedAt: string | null;
}

// ─── PipelineRun (spec §4.2) ──────────────────────────────────────────

export interface PipelineRun {
  id: string;
  pipelineId: string;
  threadId: string;
  status: "running" | "paused" | "completed" | "failed" | "cancelled";
  currentCheckpointId?: string;
  startedAt: string;
  completedAt?: string;
  error?: string;
}

// ─── Checkpoint (spec §4.3) ───────────────────────────────────────────

export interface Checkpoint {
  id: string;
  pipelineId: string;
  nodeId: string;
  state: Record<string, unknown>;
  timestamp: string;
  status: "completed" | "interrupted" | "failed";
  metadata: Record<string, unknown>;
}

// ─── Skill (spec §4.4) ────────────────────────────────────────────────

export interface Skill {
  id: string;
  name: string;
  description: string;
  category: "code" | "docs" | "infra" | "communication" | "analysis";
  type: "prompt";
  definition: { template: string; variables: string[] };
  inputs: PortDef[];
  outputs: PortDef[];
  requiredIntegrations: string[];
}

// ─── CustomTool (spec §6.4) ───────────────────────────────────────────

export interface ToolParam {
  name: string;
  type: "string" | "number" | "boolean" | "object" | "array";
  description: string;
  required: boolean;
  defaultValue?: unknown;
}

export interface CustomTool {
  id: string;
  ownerId: string;
  name: string;
  description: string;
  category: string;
  script: string;
  inputs: ToolParam[];
  outputs: ToolParam[];
  version: number;
  status: "draft" | "deployed" | "archived";
  createdAt: string;
  updatedAt: string;
}

// ─── MCP Server (spec §6.7) ───────────────────────────────────────────

export interface MCPToolInfo {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
}

export interface MCPServer {
  id: string;
  ownerId: string;
  name: string;
  description: string;
  transport: "stdio" | "sse" | "http";
  command?: string;
  url?: string;
  env: Record<string, string>;
  status: "connected" | "disconnected" | "error";
  lastConnectedAt: string | null;
  discoveredTools: MCPToolInfo[];
  createdAt: string;
  updatedAt: string;
}

// ─── Knowledge Base (spec §4.6) ───────────────────────────────────────

export interface KnowledgeBase {
  id: string;
  ownerId: string;
  name: string;
  description?: string;
  scope: "global" | "agent" | "pipeline";
  scopeRef?: string;
  source: "upload" | "vector-db" | "url" | "rivvn";
  reference: string;
  chunkSize: number;
  chunkOverlap: number;
  topK: number;
  similarityThreshold: number;
  embeddingModel: string;
  embeddingDim: number;
  documentCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface KnowledgeDocument {
  id: string;
  knowledgeBaseId: string;
  name: string;
  source: "upload" | "url";
  url?: string;
  size: number;
  chunkCount: number;
  status: "processing" | "ready" | "failed";
  createdAt: string;
}

// ─── Approval (spec §4.5) ─────────────────────────────────────────────

export interface ApprovalRequest {
  id: string;
  pipelineId: string;
  agentId: string;
  checkpointId: string;
  message: string;
  context: Record<string, unknown>;
  artifacts?: string[];
  status: "pending" | "approved" | "rejected" | "revised";
  response?: string;
  respondedBy?: string;
  respondedAt?: string;
  channel: NotificationChannel;
  sentAt: string;
  retryCount: number;
  maxRetries: number;
  attemptedChannels: NotificationChannel[];
  fallbackChannel: NotificationChannel | null;
  timeoutSeconds: number;
}

// ─── Integration (spec §4.7) ──────────────────────────────────────────

export type GitProvider = "github" | "azure";

export interface GitConnectionTestResult {
  ok: boolean;
  repositories?: number;
  error?: string;
}

export interface Integration {
  id: string;
  ownerId: string;
  type: "github" | "azure" | "gitlab";
  name: string;
  config: Record<string, unknown>;
  status: "active" | "disabled";
  createdAt: string;
  updatedAt: string;
}

// ─── Rivvn (spec §7.4) ────────────────────────────────────────────────

export interface RivvnConnection {
  ownerId: string;
  contractStatus: "active" | "inactive" | "expired";
  status: "connected" | "disconnected" | "expired";
  connectedAt: string | null;
  scope: string[];
}

// ─── Artifact (spec §4.5) ─────────────────────────────────────────────

export interface Artifact {
  id: string;
  runId: string;
  nodeId: string;
  name: string;
  type: "code" | "document" | "image" | "other";
  content: string;
  size: number;
  createdAt: string;
}

// ─── Envelope de erro (contrato §8) ───────────────────────────────────

export interface ApiErrorBody {
  error: string;
  code: string;
  details?: Record<string, unknown>;
}

// ─── Paginação (contrato §8) ──────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
}

// ─── WebSocket (contrato §7) ──────────────────────────────────────────

export type WSChannel =
  | "pipeline:status"
  | "pipeline:log"
  | "agent:output"
  | "approval:new"
  | "approval:resolved";

export interface WSFrame {
  channel: WSChannel;
  data: Record<string, unknown>;
}

export interface PipelineStatusEvent {
  pipelineId: string;
  runId: string;
  nodeId: string;
  status: "pending" | "running" | "completed" | "failed" | "waiting_approval";
  at: string;
}

export interface PipelineLogEvent {
  pipelineId: string;
  runId: string;
  nodeId: string;
  level: string;
  message: string;
  at: string;
}

export interface AgentOutputEvent {
  pipelineId: string;
  runId: string;
  nodeId: string;
  output: unknown;
}

export interface ApprovalNewEvent {
  approvalId: string;
  pipelineId: string;
  runId: string;
  nodeId: string;
  message: string;
  at: string;
}

export interface ApprovalResolvedEvent {
  approvalId: string;
  pipelineId: string;
  runId: string;
  nodeId: string;
  decision: "approved" | "rejected" | "revised";
  at: string;
}
