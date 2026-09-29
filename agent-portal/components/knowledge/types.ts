export interface KnowledgeBaseItem {
  id: string;
  name: string;
  description: string | null;
  scope: string;
  source: string;
  documentCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface KnowledgeDocument {
  id: string;
  name: string;
  status: string;
  size: number;
  chunkCount: number;
  createdAt: string;
}

export interface ChatSource {
  documentId: string;
  documentName: string;
  chunkId: string;
  text: string;
  score: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: ChatSource[];
  createdAt?: string;
}

export interface ConversationSummary {
  id: string;
  title: string;
  updatedAt: string;
  messageCount: number;
}
