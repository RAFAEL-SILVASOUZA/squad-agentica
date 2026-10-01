"use client";

import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Trash2, RefreshCw, Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import {
  AgentDetail,
  DeleteAgentModal,
} from "@/components/agents";
import { api, ApiError } from "@/lib/api";
import { getAgent, updateAgent, deleteAgent } from "@/lib/agents";
import type {
  Agent,
  Skill,
  CustomTool,
  MCPServer,
  KnowledgeBase,
  Integration,
} from "@/lib/types";

/**
 * Detalhe/edição de agente (protótipo view-AGENT-DETAIL em modo edição).
 *
 * - Carrega o agente (GET /api/agents/{id}); 404 → toast + voltar.
 * - Chat de edição (SSE) à esquerda; formulário de edição à direita.
 * - "Salvar" persiste via PUT /api/agents/{id}.
 * - Exclusão com confirmação em modal (sem window.confirm).
 *
 * Estados: loading (skeleton), 404 (empty state + voltar), erro (toast + retry).
 */

interface BackpackOptions {
  skills: Skill[];
  tools: CustomTool[];
  mcpServers: MCPServer[];
  knowledge: KnowledgeBase[];
  llmIntegrations: Integration[];
}

async function fetchBackpackOptions(): Promise<BackpackOptions> {
  const [skills, tools, mcp, knowledge, integrations] = await Promise.all([
    api.list<Skill>("/api/skills", { page: 1, limit: 100 }),
    api.list<CustomTool>("/api/tools", { page: 1, limit: 100 }),
    api.list<MCPServer>("/api/mcp-servers", { page: 1, limit: 100 }),
    api.list<KnowledgeBase>("/api/knowledge", { page: 1, limit: 100 }),
    api.list<Integration>("/api/integrations", { page: 1, limit: 100 }),
  ]);
  return {
    skills: skills.items,
    tools: tools.items,
    mcpServers: mcp.items,
    knowledge: knowledge.items,
    llmIntegrations: integrations.items.filter((i) => i.type === "llm"),
  };
}

export default function AgentDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { addToast } = useToast();
  const id = params?.id ?? "";

  const [agent, setAgent] = React.useState<Agent | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [notFound, setNotFound] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [options, setOptions] = React.useState<BackpackOptions | null>(null);
  const [saving, setSaving] = React.useState(false);
  const [deleteOpen, setDeleteOpen] = React.useState(false);
  const [deleting, setDeleting] = React.useState(false);
  const [draftId, setDraftId] = React.useState<string | null>(null);
  // Config parcial do chat de edição (config_update, spec §10). O agente
  // exibido no formulário é a fusão do agente salvo + o último config_update.
  const [chatConfig, setChatConfig] = React.useState<Partial<Agent>>({});
  const [chatStreaming, setChatStreaming] = React.useState(false);

  const handleChatConfigUpdate = React.useCallback((config: Partial<Agent>) => {
    // O modo edição do backend devolve a config COMPLETA do draft
    // (build_preview), então substitui o config anterior do chat.
    setChatConfig(config);
  }, []);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    setNotFound(false);
    try {
      const result = await getAgent(id);
      setAgent(result);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setNotFound(true);
      } else {
        const message =
          e instanceof Error ? e.message : "Falha ao carregar o agente";
        setError(message);
        addToast("error", message);
      }
    } finally {
      setLoading(false);
    }
  }, [id, addToast]);

  const loadOptions = React.useCallback(async () => {
    try {
      const result = await fetchBackpackOptions();
      setOptions(result);
    } catch {
      setOptions({ skills: [], tools: [], mcpServers: [], knowledge: [], llmIntegrations: [] });
    }
  }, []);

  React.useEffect(() => {
    void load();
    void loadOptions();
  }, [load, loadOptions]);

  const handleSaveChat = React.useCallback(async () => {
    if (!agent) return;
    const merged = { ...agent, ...chatConfig } as Agent;
    setSaving(true);
    try {
      const updated = await updateAgent(id, {
        name: merged.name,
        type: merged.type,
        description: merged.description,
        prompt: merged.prompt,
        strategy: merged.strategy,
        model: merged.model,
        maxIterations: merged.maxIterations,
        timeout: merged.timeout,
        shellAccess: merged.shellAccess,
        inputs: merged.inputs,
        outputs: merged.outputs,
        actions: merged.actions,
        skills: merged.skills,
        tools: merged.tools,
        mcpServers: merged.mcpServers,
        knowledge: merged.knowledge,
        integrations: merged.integrations,
      });
      setAgent(updated);
      setChatConfig({});
      addToast("success", "Agente atualizado.");
    } catch (e) {
      addToast("error", e instanceof Error ? e.message : "Falha ao salvar o agente.");
    } finally {
      setSaving(false);
    }
  }, [agent, chatConfig, id, addToast]);

  const handleSave = React.useCallback(
    async (payload: Parameters<typeof updateAgent>[1]) => {
      setSaving(true);
      try {
        const updated = await updateAgent(id, payload);
        setAgent(updated);
        setChatConfig({});
        addToast("success", "Agente atualizado.");
      } finally {
        setSaving(false);
      }
    },
    [id, addToast]
  );

  const handleDelete = React.useCallback(async () => {
    setDeleting(true);
    try {
      await deleteAgent(id);
      addToast("success", "Agente excluído.");
      router.push("/");
    } catch (e) {
      addToast(
        "error",
        e instanceof Error ? e.message : "Falha ao excluir o agente."
      );
      setDeleting(false);
      setDeleteOpen(false);
    }
  }, [id, addToast, router]);

  if (loading) {
    return (
      <div>
        <div style={{ height: 24, width: 200, marginBottom: 20 }}>
          <Skeleton width={200} height={24} />
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))",
            gap: "16px",
          }}
        >
          <Skeleton width="100%" height={360} />
          <Skeleton width="100%" height={360} />
        </div>
      </div>
    );
  }

  if (notFound) {
    return (
      <div>
        <div style={{ marginBottom: "20px" }}>
          <Link href="/">
            <Button size="sm" aria-label="Voltar para o dashboard">
              <ArrowLeft size={14} aria-hidden="true" />
              Voltar
            </Button>
          </Link>
        </div>
        <EmptyState
          icon={Bot}
          title="Agente não encontrado"
          description="Este agente não existe ou não pertence à sua conta."
          action={
            <Link href="/">
              <Button>Voltar ao dashboard</Button>
            </Link>
          }
        />
      </div>
    );
  }

  if (error || !agent) {
    return (
      <div>
        <div style={{ marginBottom: "20px" }}>
          <Link href="/">
            <Button size="sm" aria-label="Voltar para o dashboard">
              <ArrowLeft size={14} aria-hidden="true" />
              Voltar
            </Button>
          </Link>
        </div>
        <Card>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "12px",
            }}
          >
            <span style={{ fontSize: "13px", color: "var(--error)" }}>
              {error ?? "Falha ao carregar o agente."}
            </span>
            <Button size="sm" onClick={() => void load()}>
              <RefreshCw size={13} aria-hidden="true" />
              Tentar novamente
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div>
      {/* Breadcrumb */}
      <Breadcrumb items={[{ label: "Agentes", href: "/agents" }, { label: agent.name }]} />

      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "16px",
          marginBottom: "20px",
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <Link href="/">
            <Button size="sm" aria-label="Voltar para o dashboard">
              <ArrowLeft size={14} aria-hidden="true" />
              Voltar
            </Button>
          </Link>
          <div>
            <h1
              style={{
                fontSize: "20px",
                fontWeight: 700,
                color: "var(--text)",
                margin: 0,
              }}
            >
              {agent.name}
            </h1>
            <p
              style={{
                fontSize: "12px",
                color: "var(--text-secondary)",
                margin: "4px 0 0",
              }}
            >
              {agent.type}
            </p>
          </div>
        </div>
        <Button size="sm" onClick={() => setDeleteOpen(true)}>
          <Trash2 size={14} aria-hidden="true" />
          Excluir
        </Button>
      </div>

      {/* Detalhe do agente em abas (inclui Conversar com chat + preview) */}
      <AgentDetail
        agent={
          Object.keys(chatConfig).length > 0
            ? ({ ...agent, ...chatConfig } as Agent)
            : agent
        }
        options={options ?? { skills: [], tools: [], mcpServers: [], knowledge: [], llmIntegrations: [] }}
        onSave={handleSave}
        saving={saving}
        chatPath={`/api/agents/${agent.id}/chat`}
        draftId={draftId}
        onDraftId={setDraftId}
        onConfigUpdate={handleChatConfigUpdate}
        onStreamingChange={setChatStreaming}
        initialAssistantMessage={`Olá! Posso ajudar a ajustar o agente "${agent.name}". O que você quer mudar?`}
        chatConfig={chatConfig}
        chatStreaming={chatStreaming}
        onSaveChat={() => void handleSaveChat()}
        onDiscardChat={() => setChatConfig({})}
      />

      <DeleteAgentModal
        open={deleteOpen}
        agentName={agent.name}
        deleting={deleting}
        onConfirm={() => void handleDelete()}
        onCancel={() => setDeleteOpen(false)}
      />
    </div>
  );
}
