"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, CheckCircle2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { useToast } from "@/components/ui/toast";
import { AgentChat, AgentPreview } from "@/components/agents";
import { api } from "@/lib/api";
import { confirmAgentDraft } from "@/lib/agent-chat";
import type {
  Agent,
  Skill,
  CustomTool,
  MCPServer,
  KnowledgeBase,
} from "@/lib/types";

/**
 * Criar novo agente (protótipo view-AGENT-DETAIL em modo "Criar novo").
 *
 * - Chat de construção (SSE) à esquerda; preview do draft à direita.
 * - "Salvar" confirma o draft (POST /api/agents/chat/confirm) e navega
 *   para /agents/{id}. Confirmação antes de salvar (botão explícito).
 *
 * Portal nasce vazio (contrato §0): sem seed ilustrativo.
 * Estados: loading (skeleton da mochila), erro (toast + retry).
 */

interface BackpackOptions {
  skills: Skill[];
  tools: CustomTool[];
  mcpServers: MCPServer[];
  knowledge: KnowledgeBase[];
}

async function fetchBackpackOptions(): Promise<BackpackOptions> {
  const [skills, tools, mcp, knowledge] = await Promise.all([
    api.list<Skill>("/api/skills", { page: 1, limit: 100 }),
    api.list<CustomTool>("/api/tools", { page: 1, limit: 100 }),
    api.list<MCPServer>("/api/mcp-servers", { page: 1, limit: 100 }),
    api.list<KnowledgeBase>("/api/knowledge", { page: 1, limit: 100 }),
  ]);
  return {
    skills: skills.items,
    tools: tools.items,
    mcpServers: mcp.items,
    knowledge: knowledge.items,
  };
}

export default function NewAgentPage() {
  const router = useRouter();
  const { addToast } = useToast();

  const [draftId, setDraftId] = React.useState<string | null>(null);
  const [config, setConfig] = React.useState<Partial<Agent>>({});
  const [saving, setSaving] = React.useState(false);
  const [options, setOptions] = React.useState<BackpackOptions | null>(null);
  const [optionsError, setOptionsError] = React.useState(false);

  const loadOptions = React.useCallback(async () => {
    setOptionsError(false);
    try {
      const result = await fetchBackpackOptions();
      setOptions(result);
    } catch {
      // Sem opções da mochila: o chat ainda funciona (o agente pode ser
      // criado sem skills/tools). Não bloqueia a tela.
      setOptions({ skills: [], tools: [], mcpServers: [], knowledge: [] });
      setOptionsError(true);
    }
  }, []);

  React.useEffect(() => {
    void loadOptions();
  }, [loadOptions]);

  const handleConfigUpdate = React.useCallback((partial: Partial<Agent>) => {
    setConfig((prev) => ({ ...prev, ...partial }));
  }, []);

  // E2: rascunho utilizável = tem NOME (espelha a regra do backend em
  // /api/agents/chat/confirm: 400 incomplete_draft sem nome). Sem isso, o
  // confirm criava "Unnamed Agent" no banco.
  const draftUsable = Boolean(
    draftId && String(config.name ?? "").trim().length > 0
  );

  const handleSave = React.useCallback(async () => {
    if (!draftId) {
      addToast("warning", "Converse com o assistente antes de salvar.");
      return;
    }
    setSaving(true);
    try {
      const agent = await confirmAgentDraft(draftId);
      addToast("success", `Agente "${agent.name}" criado.`);
      router.push(`/agents/${agent.id}`);
    } catch (e) {
      addToast(
        "error",
        e instanceof Error ? e.message : "Falha ao salvar o agente."
      );
      setSaving(false);
    }
  }, [draftId, addToast, router]);

  return (
    <div>
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
              Novo Agente
            </h1>
            <p
              style={{
                fontSize: "12px",
                color: "var(--text-secondary)",
                margin: "4px 0 0",
              }}
            >
              Construa o agente conversando com o assistente.
            </p>
          </div>
        </div>
        <Button
          variant="primary"
          onClick={() => void handleSave()}
          loading={saving}
          // E2: sem draft utilizável (nome + prompt no config), salvar é
          // inútil: o backend recusa (400 incomplete_draft). O botão só
          // habilita quando o rascunho está utilizável.
          disabled={!draftId || !draftUsable}
        >
          <CheckCircle2 size={14} aria-hidden="true" />
          Salvar agente
        </Button>
      </div>

      {/* Aviso de erro ao carregar a mochila */}
      {optionsError && (
        <Card style={{ marginBottom: "16px" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "12px",
            }}
          >
            <span style={{ fontSize: "13px", color: "var(--warning)" }}>
              Não foi possível carregar skills, tools e bases de conhecimento.
              O chat continua disponível.
            </span>
            <Button size="sm" onClick={() => void loadOptions()}>
              <RefreshCw size={13} aria-hidden="true" />
              Tentar novamente
            </Button>
          </div>
        </Card>
      )}

      {/* Chat + preview */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))",
          gap: "16px",
          alignItems: "start",
        }}
      >
        <AgentChat
          chatPath="/api/agents/chat"
          draftId={draftId}
          onDraftId={setDraftId}
          onConfigUpdate={handleConfigUpdate}
          initialAssistantMessage="Olá! Descreva o agente que você quer criar: o que ele faz, quais skills e integrações precisa, e qual contrato de fluxo (entradas, saídas, ações)."
        />
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          <h2
            style={{
              fontSize: "13px",
              fontWeight: 600,
              color: "var(--text-secondary)",
              textTransform: "uppercase",
              letterSpacing: "0.5px",
              margin: 0,
            }}
          >
            Preview do agente
          </h2>
          <AgentPreview config={config} />
          {!draftId && (
            <EmptyState
              title="Ainda sem rascunho"
              description="Envie uma mensagem no chat para o assistente gerar o rascunho do agente. O botão Salvar habilita após o primeiro rascunho."
            />
          )}
          {draftId && !draftUsable && (
            <EmptyState
              title="Rascunho incompleto"
              description="O assistente ainda não definiu o nome do agente. Continue a conversa (ex.: 'o agente se chama X e deve fazer Y') para habilitar o botão Salvar."
            />
          )}
        </div>
      </div>
    </div>
  );
}
