"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Toggle } from "@/components/ui/toggle";
import { Card } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import { ErrorPanel } from "@/components/ui/error-panel";
import { ApiError } from "@/lib/api";
import type {
  Agent,
  PortDef,
  SkillRef,
  ToolRef,
  MCPServerRef,
  KnowledgeRef,
  IntegrationRef,
  Integration,
  FlowAction,
  Skill,
  CustomTool,
  MCPServer,
  KnowledgeBase,
  NotificationChannel,
} from "@/lib/types";
import type { AgentUpdatePayload } from "@/lib/agents";
import { PortsEditor } from "@/components/ports/ports-editor";
import { AgentChat } from "./agent-chat";
import { AgentPreview } from "./agent-preview";

/**
 * Detalhe/edição do agente (protótipo view-AGENT-DETAIL).
 *
 * - Identidade: nome, tipo, descrição, prompt, strategy.
 * - Contrato de fluxo: inputs, outputs (PortDef), actions (follow/return/finalize).
 * - Execução: modelo, maxIterations, timeout, shellAccess, canal de aprovação.
 * - Mochila: skills, tools, MCP, knowledge, integrações (seletores que listam
 *   o que o usuário já cadastrou).
 *
 * Sem emojis; ícones via lucide-react. Labels em todos os campos.
 */

export interface BackpackOptions {
  skills: Skill[];
  tools: CustomTool[];
  mcpServers: MCPServer[];
  knowledge: KnowledgeBase[];
  /** Integrações LLM cadastradas (adendo 8), para o seletor de modelo. */
  llmIntegrations?: Integration[];
}

export interface AgentDetailProps {
  /** Agente carregado (edição) ou undefined (novo). */
  agent?: Agent;
  /** Opções da mochila (o que o usuário já cadastrou). */
  options: BackpackOptions;
  /** Chamado ao salvar. */
  onSave: (payload: AgentUpdatePayload) => Promise<void>;
  /** true enquanto salva. */
  saving?: boolean;
  /**
   * Key que força re-inicialização do formulário a partir da prop `agent`.
   */
  resetKey?: string | number;
  // ── Conversar tab ──────────────────────────────────────────────
  chatPath?: string;
  draftId?: string | null;
  onDraftId?: (id: string) => void;
  onConfigUpdate?: (config: Partial<Agent>) => void;
  onStreamingChange?: (streaming: boolean) => void;
  initialAssistantMessage?: string;
  /** Config parcial do chat (config_update). */
  chatConfig?: Partial<Agent>;
  /** true enquanto o chat está streamando. */
  chatStreaming?: boolean;
  /** Salva as alterações do chat. */
  onSaveChat?: () => void;
  /** Descarta as alterações do chat. */
  onDiscardChat?: () => void;
}

const FLOW_ACTIONS: { value: FlowAction; label: string }[] = [
  { value: "follow", label: "Seguir" },
  { value: "return", label: "Devolver" },
  { value: "finalize", label: "Finalizar" },
];

const APPROVAL_CHANNELS: { value: NotificationChannel; label: string }[] = [
  { value: "in-app", label: "In-app" },
  { value: "email", label: "Email" },
  { value: "teams", label: "Teams" },
  { value: "slack", label: "Slack" },
];

const INTEGRATION_PLATFORMS: IntegrationRef["platform"][] = [
  "azure",
  "github",
  "gitlab",
  "azure-devops",
  "email",
  "custom",
];

const PORT_TYPE_OPTIONS = ["document", "code", "artifact", "signal"];

// ── Tabs ──────────────────────────────────────────────────────────────────────

const TABS = [
  { id: "visao-geral", label: "Visão geral" },
  { id: "conversar", label: "Conversar" },
  { id: "contrato", label: "Contrato" },
  { id: "mochila", label: "Mochila" },
  { id: "execucao", label: "Execução" },
] as const;

type TabId = (typeof TABS)[number]["id"];

function validTab(value: string | null): TabId {
  const found = TABS.find((t) => t.id === value);
  return found ? found.id : "visao-geral";
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h3
      style={{
        fontSize: "12px",
        fontWeight: 600,
        color: "var(--text-secondary)",
        textTransform: "uppercase",
        letterSpacing: "0.5px",
        margin: "0 0 10px",
      }}
    >
      {children}
    </h3>
  );
}

function Chip({ label, onRemove }: { label: string; onRemove?: () => void }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "4px",
        fontSize: "11px",
        color: "var(--text)",
        background: "var(--bg-hover)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "10px",
        padding: "2px 8px",
      }}
    >
      {label}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remover ${label}`}
          style={{
            background: "none",
            border: "none",
            color: "var(--text-muted)",
            cursor: "pointer",
            padding: 0,
            display: "flex",
            alignItems: "center",
          }}
        >
          <X size={11} aria-hidden="true" />
        </button>
      )}
    </span>
  );
}

/** Hook: true quando a viewport é < 768px. */
function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = React.useState(false);
  React.useEffect(() => {
    const mql = window.matchMedia("(max-width: 767px)");
    setIsMobile(mql.matches);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, []);
  return isMobile;
}

export function AgentDetail({
  agent,
  options,
  onSave,
  saving = false,
  chatPath,
  draftId,
  onDraftId,
  onConfigUpdate,
  onStreamingChange,
  initialAssistantMessage,
  chatConfig,
  chatStreaming = false,
  onSaveChat,
  onDiscardChat,
}: AgentDetailProps) {
  const { addToast } = useToast();
  const router = useRouter();
  const params = useSearchParams();
  const isMobile = useIsMobile();

  const queryTab = params.get("tab");
  const [activeTab, setActiveTab] = React.useState<TabId>(() => validTab(queryTab));

  React.useEffect(() => {
    setActiveTab(validTab(queryTab));
  }, [queryTab]);

  const selectTab = (tab: TabId) => {
    setActiveTab(tab);
    const next = new URLSearchParams(params.toString());
    next.set("tab", tab);
    router.replace(`?${next.toString()}`, { scroll: false });
  };

  const [name, setName] = React.useState(agent?.name ?? "");
  const [type, setType] = React.useState(agent?.type ?? "custom");
  const [description, setDescription] = React.useState(agent?.description ?? "");
  const [prompt, setPrompt] = React.useState(agent?.prompt ?? "");
  const [strategy, setStrategy] = React.useState(agent?.strategy ?? "");
  const [model, setModel] = React.useState(agent?.model ?? "gpt-4o");
  // Escolha opcional de LLM por agente (adendo 8): integração + modelo.
  // Vazio = o agente usa o fallback (padrão do usuário > ambiente).
  const [llmIntegrationId, setLlmIntegrationId] = React.useState(
    agent?.llm?.integrationId ?? ""
  );
  const [llmModel, setLlmModel] = React.useState(agent?.llm?.model ?? "");
  const [maxIterations, setMaxIterations] = React.useState(
    String(agent?.maxIterations ?? 10)
  );
  const [timeout, setTimeout_] = React.useState(String(agent?.timeout ?? 300));
  const [shellAccess, setShellAccess] = React.useState(agent?.shellAccess ?? false);
  const [approvalChannel, setApprovalChannel] = React.useState<NotificationChannel>(
    "in-app"
  );

  const [inputs, setInputs] = React.useState<PortDef[]>(agent?.inputs ?? []);
  const [outputs, setOutputs] = React.useState<PortDef[]>(agent?.outputs ?? []);
  const [actions, setActions] = React.useState<FlowAction[]>(agent?.actions ?? []);

  const [skills, setSkills] = React.useState<SkillRef[]>(agent?.skills ?? []);
  const [tools, setTools] = React.useState<ToolRef[]>(agent?.tools ?? []);
  const [mcpServers, setMcpServers] = React.useState<MCPServerRef[]>(
    agent?.mcpServers ?? []
  );
  const [knowledge, setKnowledge] = React.useState<KnowledgeRef[]>(
    agent?.knowledge ?? []
  );
  const [integrations, setIntegrations] = React.useState<IntegrationRef[]>(
    agent?.integrations ?? []
  );

  const [skillSel, setSkillSel] = React.useState("");
  const [toolSel, setToolSel] = React.useState("");
  const [mcpSel, setMcpSel] = React.useState("");
  const [knowledgeSel, setKnowledgeSel] = React.useState("");
  const [integrationSel, setIntegrationSel] = React.useState("");

  const [nameError, setNameError] = React.useState<string | undefined>();
  const [saveError, setSaveError] = React.useState<{ message: string; detail?: string } | null>(null);

  React.useEffect(() => {
    if (!agent) return;
    setName(agent.name);
    setType(agent.type);
    setDescription(agent.description);
    setPrompt(agent.prompt);
    setStrategy(agent.strategy);
    setModel(agent.model);
    setLlmIntegrationId(agent.llm?.integrationId ?? "");
    setLlmModel(agent.llm?.model ?? "");
    setMaxIterations(String(agent.maxIterations));
    setTimeout_(String(agent.timeout));
    setShellAccess(agent.shellAccess);
    setInputs(agent.inputs ?? []);
    setOutputs(agent.outputs ?? []);
    setActions(agent.actions ?? []);
    setSkills(agent.skills ?? []);
    setTools(agent.tools ?? []);
    setMcpServers(agent.mcpServers ?? []);
    setKnowledge(agent.knowledge ?? []);
    setIntegrations(agent.integrations ?? []);
  }, [agent]);

  const skillOptions = options.skills.map((s) => ({ value: s.id, label: s.name }));
  const toolOptions = options.tools.map((t) => ({ value: t.id, label: t.name }));
  const mcpOptions = options.mcpServers.map((m) => ({ value: m.id, label: m.name }));
  const knowledgeOptions = options.knowledge.map((k) => ({
    value: k.id,
    label: k.name,
  }));

  // Modelos disponíveis na integração LLM escolhida (adendo 8).
  const llmIntegrations = options.llmIntegrations ?? [];
  const selectedLlmIntegration = llmIntegrations.find(
    (i) => i.id === llmIntegrationId
  );
  const llmModelOptions = React.useMemo(() => {
    if (!selectedLlmIntegration) return [] as { value: string; label: string }[];
    const cfg = selectedLlmIntegration.config;
    const models = Array.isArray(cfg.models)
      ? cfg.models.map((m) => String(m)).filter(Boolean)
      : [];
    const defaultModel = typeof cfg.default_model === "string" ? cfg.default_model : "";
    const set = new Set(models);
    if (defaultModel) set.add(defaultModel);
    return Array.from(set).map((m) => ({ value: m, label: m }));
  }, [selectedLlmIntegration]);

  const nameOf = (list: { value: string; label: string }[], id: string) =>
    list.find((o) => o.value === id)?.label ?? id;

  // Ao trocar a integração, o modelo escolhido pode não existir nela: limpa.
  React.useEffect(() => {
    if (!llmIntegrationId) return;
    if (!llmModelOptions.some((o) => o.value === llmModel)) setLlmModel("");
  }, [llmIntegrationId, llmModelOptions, llmModel]);

  const effectiveModel = agent?.effectiveModel ?? agent?.model;
  const configuredModel = agent?.model;
  const modelDiffers =
    effectiveModel && configuredModel && effectiveModel !== configuredModel;

  const toggleAction = (action: FlowAction) => {
    setActions((prev) =>
      prev.includes(action)
        ? prev.filter((a) => a !== action)
        : [...prev, action]
    );
  };

  const addSkill = () => {
    if (!skillSel) return;
    if (skills.some((s) => s.skillId === skillSel)) {
      addToast("warning", "Skill já adicionada.");
      return;
    }
    setSkills((prev) => [...prev, { skillId: skillSel, config: {} }]);
    setSkillSel("");
  };

  const addTool = () => {
    if (!toolSel) return;
    if (tools.some((t) => t.toolId === toolSel)) {
      addToast("warning", "Tool já adicionada.");
      return;
    }
    setTools((prev) => [...prev, { toolId: toolSel, config: {} }]);
    setToolSel("");
  };

  const addMcp = () => {
    if (!mcpSel) return;
    if (mcpServers.some((m) => m.serverId === mcpSel)) {
      addToast("warning", "Servidor MCP já adicionado.");
      return;
    }
    setMcpServers((prev) => [...prev, { serverId: mcpSel }]);
    setMcpSel("");
  };

  const addKnowledge = () => {
    if (!knowledgeSel) return;
    const kb = options.knowledge.find((k) => k.id === knowledgeSel);
    if (!kb) return;
    if (knowledge.some((k) => k.reference === kb.id)) {
      addToast("warning", "Base de conhecimento já adicionada.");
      return;
    }
    setKnowledge((prev) => [
      ...prev,
      { source: kb.source, reference: kb.id },
    ]);
    setKnowledgeSel("");
  };

  const addIntegration = () => {
    if (!integrationSel) return;
    const platform = integrationSel as IntegrationRef["platform"];
    if (integrations.some((i) => i.platform === platform)) {
      addToast("warning", "Integração já adicionada.");
      return;
    }
    setIntegrations((prev) => [...prev, { platform, config: {} }]);
    setIntegrationSel("");
  };

  const handleSave = async () => {
    if (!name.trim()) {
      setNameError("Informe um nome para o agente.");
      return;
    }
    setNameError(undefined);

    const maxIter = parseInt(maxIterations, 10);
    const timeoutNum = parseInt(timeout, 10);

    const payload: AgentUpdatePayload = {
      name: name.trim(),
      type,
      description,
      prompt,
      strategy,
      model,
      // Adendo 8: escolha opcional de LLM. Sem integração = fallback (usuário/ambiente).
      llm: llmIntegrationId ? { integrationId: llmIntegrationId, ...(llmModel ? { model: llmModel } : {}) } : null,
      maxIterations: Number.isFinite(maxIter) ? maxIter : 10,
      timeout: Number.isFinite(timeoutNum) ? timeoutNum : 300,
      shellAccess,
      inputs: inputs.filter((p) => p.name.trim()),
      outputs: outputs.filter((p) => p.name.trim()),
      actions,
      skills,
      tools,
      mcpServers,
      knowledge,
      integrations,
    };

    setSaveError(null);
    try {
      await onSave(payload);
    } catch (e) {
      setSaveError({
        message: "Não foi possível salvar o agente",
        detail: e instanceof ApiError ? e.describe() : undefined,
      });
    }
  };

  // ── Tab panels ──────────────────────────────────────────────────────────────

  const visaoGeralPanel = (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {effectiveModel && (
        <Card>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", padding: "12px 14px" }}>
            <span
              aria-hidden="true"
              style={{
                width: 32, height: 32, borderRadius: "var(--radius-sm)",
                background: "var(--accent-subtle)", color: "var(--accent)",
                display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 9h6v6H9z"/></svg>
            </span>
            <div>
              <div style={{ fontSize: "11px", color: "var(--text-secondary)", marginBottom: "2px" }}>Modelo</div>
              <div style={{ fontSize: "14px", fontWeight: 600, color: "var(--text)" }}>{effectiveModel}</div>
              {modelDiffers && (
                <div style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "2px" }}>
                  Configurado: {configuredModel} · o servidor usa {effectiveModel}
                </div>
              )}
            </div>
          </div>
        </Card>
      )}
      <Card>
        <SectionTitle>Identidade</SectionTitle>
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          <Input label="Nome" value={name} onChange={(e) => setName(e.target.value)} error={nameError} placeholder="Ex.: Backend Developer" />
          <Input label="Tipo" value={type} onChange={(e) => setType(e.target.value)} placeholder="Ex.: Developer" />
          <Textarea label="Descrição" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} placeholder="O que este agente faz?" />
          <Textarea label="Prompt" value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={4} placeholder="Instruções do sistema para o agente" />
          <Textarea label="Strategy" value={strategy} onChange={(e) => setStrategy(e.target.value)} rows={2} placeholder="Estratégia de execução" />
        </div>
      </Card>
    </div>
  );

  const conversarPanel = (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {chatConfig && Object.keys(chatConfig).length > 0 && !chatStreaming && (
        <div
          role="status"
          style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            gap: "12px", padding: "10px 14px", borderRadius: "var(--radius)",
            border: "1px solid var(--warning)", background: "var(--bg-card)", fontSize: "13px",
          }}
        >
          <span>Alterações do assistente ainda não salvas.</span>
          <div style={{ display: "flex", gap: "8px" }}>
            <Button size="sm" onClick={onDiscardChat} disabled={saving}>Descartar</Button>
            <Button size="sm" variant="primary" loading={saving} onClick={onSaveChat}>Salvar alterações</Button>
          </div>
        </div>
      )}
      {agent && (
        <AgentPreview
          config={
            chatConfig && Object.keys(chatConfig).length > 0
              ? ({ ...agent, ...chatConfig } as Agent)
              : agent
          }
          streaming={chatStreaming}
        />
      )}
      {chatPath && (
        <AgentChat
          chatPath={chatPath}
          draftId={draftId ?? null}
          onDraftId={onDraftId}
          onConfigUpdate={onConfigUpdate}
          onStreamingChange={onStreamingChange}
          initialAssistantMessage={initialAssistantMessage}
          stickyInput={isMobile}
        />
      )}
    </div>
  );

  const contratoPanel = (
    <Card>
      <SectionTitle>Contrato de Fluxo</SectionTitle>
      <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
        <PortsEditor label="Entradas" value={inputs} onChange={setInputs} types={PORT_TYPE_OPTIONS} />
        <PortsEditor label="Saídas" value={outputs} onChange={setOutputs} types={PORT_TYPE_OPTIONS} />
        <div>
          <span style={{ fontSize: "12px", fontWeight: 500, color: "var(--text)", display: "block", marginBottom: "8px" }}>Ações</span>
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
            {FLOW_ACTIONS.map((a) => {
              const active = actions.includes(a.value);
              return (
                <button
                  key={a.value}
                  type="button"
                  onClick={() => toggleAction(a.value)}
                  aria-pressed={active}
                  style={{
                    padding: "6px 12px", borderRadius: "var(--radius-sm)",
                    border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
                    background: active ? "var(--accent-subtle)" : "var(--bg-card)",
                    color: active ? "var(--accent)" : "var(--text-secondary)",
                    fontSize: "12px", fontWeight: 500, cursor: "pointer", transition: "all var(--transition)",
                  }}
                >
                  {a.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </Card>
  );

  const mochilaPanel = (
    <Card>
      <SectionTitle>Mochila</SectionTitle>
      <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
        <div>
          <span style={{ fontSize: "12px", fontWeight: 500, color: "var(--text)", display: "block", marginBottom: "6px" }}>Skills</span>
          <div style={{ display: "flex", gap: "6px", marginBottom: "8px" }}>
            <Select aria-label="Selecionar skill" value={skillSel} onValueChange={setSkillSel} options={skillOptions} placeholder={options.skills.length ? "Escolher skill…" : "Nenhuma skill cadastrada"} />
            <Button size="sm" onClick={addSkill} disabled={!skillSel} aria-label="Adicionar skill"><Plus size={12} aria-hidden="true" /></Button>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "4px", alignItems: "center" }}>
            {skills.length === 0 && (
              <>
                <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>Nenhuma skill associada.</span>
                <Link href="/skills?new=1" target="_blank" style={{ fontSize: "11px", color: "var(--accent)", textDecoration: "none", fontWeight: 500 }}>Criar skill →</Link>
              </>
            )}
            {skills.map((s) => (
              <Chip key={s.skillId} label={nameOf(skillOptions, s.skillId)} onRemove={() => setSkills((prev) => prev.filter((x) => x.skillId !== s.skillId))} />
            ))}
          </div>
        </div>
        <div>
          <span style={{ fontSize: "12px", fontWeight: 500, color: "var(--text)", display: "block", marginBottom: "6px" }}>Tools Custom</span>
          <div style={{ display: "flex", gap: "6px", marginBottom: "8px" }}>
            <Select aria-label="Selecionar tool" value={toolSel} onValueChange={setToolSel} options={toolOptions} placeholder={options.tools.length ? "Escolher tool…" : "Nenhuma tool cadastrada"} />
            <Button size="sm" onClick={addTool} disabled={!toolSel} aria-label="Adicionar tool"><Plus size={12} aria-hidden="true" /></Button>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "4px", alignItems: "center" }}>
            {tools.length === 0 && (
              <>
                <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>Nenhuma tool associada.</span>
                <Link href="/tools?new=1" target="_blank" style={{ fontSize: "11px", color: "var(--accent)", textDecoration: "none", fontWeight: 500 }}>Criar tool →</Link>
              </>
            )}
            {tools.map((t) => (
              <Chip key={t.toolId} label={nameOf(toolOptions, t.toolId)} onRemove={() => setTools((prev) => prev.filter((x) => x.toolId !== t.toolId))} />
            ))}
          </div>
        </div>
        <div>
          <span style={{ fontSize: "12px", fontWeight: 500, color: "var(--text)", display: "block", marginBottom: "6px" }}>Servidores MCP</span>
          <div style={{ display: "flex", gap: "6px", marginBottom: "8px" }}>
            <Select aria-label="Selecionar servidor MCP" value={mcpSel} onValueChange={setMcpSel} options={mcpOptions} placeholder={options.mcpServers.length ? "Escolher servidor…" : "Nenhum servidor cadastrado"} />
            <Button size="sm" onClick={addMcp} disabled={!mcpSel} aria-label="Adicionar servidor MCP"><Plus size={12} aria-hidden="true" /></Button>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
            {mcpServers.length === 0 && (
              <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>Nenhum servidor MCP associado.</span>
            )}
            {mcpServers.map((m) => (
              <Chip key={m.serverId} label={nameOf(mcpOptions, m.serverId)} onRemove={() => setMcpServers((prev) => prev.filter((x) => x.serverId !== m.serverId))} />
            ))}
          </div>
        </div>
        <div>
          <span style={{ fontSize: "12px", fontWeight: 500, color: "var(--text)", display: "block", marginBottom: "6px" }}>Knowledge</span>
          <div style={{ display: "flex", gap: "6px", marginBottom: "8px" }}>
            <Select aria-label="Selecionar base de conhecimento" value={knowledgeSel} onValueChange={setKnowledgeSel} options={knowledgeOptions} placeholder={options.knowledge.length ? "Escolher base…" : "Nenhuma base cadastrada"} />
            <Button size="sm" onClick={addKnowledge} disabled={!knowledgeSel} aria-label="Adicionar base de conhecimento"><Plus size={12} aria-hidden="true" /></Button>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "4px", alignItems: "center" }}>
            {knowledge.length === 0 && (
              <>
                <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>Nenhuma base de conhecimento associada.</span>
                <Link href="/knowledge?new=1" target="_blank" style={{ fontSize: "11px", color: "var(--accent)", textDecoration: "none", fontWeight: 500 }}>Criar base →</Link>
              </>
            )}
            {knowledge.map((k) => (
              <Chip key={k.reference} label={nameOf(knowledgeOptions, k.reference)} onRemove={() => setKnowledge((prev) => prev.filter((x) => x.reference !== k.reference))} />
            ))}
          </div>
        </div>
        <div>
          <span style={{ fontSize: "12px", fontWeight: 500, color: "var(--text)", display: "block", marginBottom: "6px" }}>Integrações</span>
          <div style={{ display: "flex", gap: "6px", marginBottom: "8px" }}>
            <Select aria-label="Selecionar integração" value={integrationSel} onValueChange={setIntegrationSel} options={INTEGRATION_PLATFORMS.map((p) => ({ value: p, label: p }))} placeholder="Escolher plataforma…" />
            <Button size="sm" onClick={addIntegration} disabled={!integrationSel} aria-label="Adicionar integração"><Plus size={12} aria-hidden="true" /></Button>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
            {integrations.length === 0 && (
              <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>Nenhuma integração associada.</span>
            )}
            {integrations.map((integ) => (
              <Chip key={integ.platform} label={integ.platform} onRemove={() => setIntegrations((prev) => prev.filter((x) => x.platform !== integ.platform))} />
            ))}
          </div>
        </div>
      </div>
    </Card>
  );

  const execucaoPanel = (
    <Card>
      <SectionTitle>Execução</SectionTitle>
      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        <Input label="Modelo configurado" value={model} onChange={(e) => setModel(e.target.value)} placeholder="Ex.: gpt-4o" />
        <div style={{ display: "flex", flexDirection: "column", gap: "8px", padding: "12px 14px", borderRadius: "var(--radius-sm)", border: "1px solid var(--border-subtle)", background: "var(--bg-card)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px" }}>
            <span style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.5px" }}>Modelo LLM (opcional)</span>
            {effectiveModel && (
              <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>em uso: <code style={{ fontFamily: "var(--font-mono)" }}>{effectiveModel}</code></span>
            )}
          </div>
          {llmIntegrations.length === 0 ? (
            <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
              Nenhuma conexão LLM cadastrada. O agente usa o padrão do usuário ou do ambiente.
              <Link href="/integrations?tab=llm" target="_blank" style={{ color: "var(--accent)", textDecoration: "none", fontWeight: 500, marginLeft: "4px" }}>Criar conexão →</Link>
            </span>
          ) : (
            <>
              <Select
                aria-label="Conexão LLM"
                value={llmIntegrationId}
                onValueChange={setLlmIntegrationId}
                options={[
                  { value: "", label: "Padrão (usuário/ambiente)" },
                  ...llmIntegrations.map((i) => ({ value: i.id, label: i.name })),
                ]}
              />
              {llmIntegrationId && (
                <Select
                  aria-label="Modelo da conexão LLM"
                  value={llmModel}
                  onValueChange={setLlmModel}
                  options={[
                    { value: "", label: "Padrão da conexão" },
                    ...llmModelOptions,
                  ]}
                />
              )}
              <p style={{ fontSize: "11px", color: "var(--text-muted)", margin: 0 }}>
                Opcional: sem escolha, o agente usa o padrão do usuário e, depois, o do ambiente.
              </p>
            </>
          )}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          <Input label="Max iterações" type="number" min={1} max={1000} value={maxIterations} onChange={(e) => setMaxIterations(e.target.value)} />
          <Input label="Timeout (s)" type="number" min={1} max={3600} value={timeout} onChange={(e) => setTimeout_(e.target.value)} />
        </div>
        <Select label="Canal de aprovação" value={approvalChannel} onValueChange={(v) => setApprovalChannel(v as NotificationChannel)} options={APPROVAL_CHANNELS} />
        <Toggle
          label="Acesso a shell"
          description="Permite ao agente executar comandos no shell. Use só em ambiente confiável e de um único usuário: o shell não tem sandbox e pode ler os workspaces de outras execuções no volume compartilhado."
          checked={shellAccess}
          onChange={setShellAccess}
        />
      </div>
    </Card>
  );

  const panels: Record<TabId, React.ReactNode> = {
    "visao-geral": visaoGeralPanel,
    conversar: conversarPanel,
    contrato: contratoPanel,
    mochila: mochilaPanel,
    execucao: execucaoPanel,
  };

  return (
    <div data-agent-detail style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {saveError && (
        <ErrorPanel title={saveError.message} detail={saveError.detail} onRetry={() => void handleSave()} />
      )}
      <div
        role="tablist"
        aria-label="Seções do agente"
        style={{ display: "flex", gap: "4px", flexWrap: "wrap", borderBottom: "1px solid var(--border)", paddingBottom: "8px" }}
      >
        {TABS.map((tab) => {
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              id={`agent-tab-${tab.id}`}
              role="tab"
              aria-selected={active}
              aria-controls={`agent-panel-${tab.id}`}
              tabIndex={active ? 0 : -1}
              onClick={() => selectTab(tab.id)}
              style={{
                padding: "8px 14px", borderRadius: "var(--radius-sm)",
                border: "1px solid transparent",
                background: active ? "var(--accent-subtle)" : "transparent",
                color: active ? "var(--accent)" : "var(--text-secondary)",
                fontSize: "13px", fontWeight: 500, cursor: "pointer",
                transition: "all var(--transition)",
                minWidth: "44px", minHeight: "44px",
              }}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      <div role="tabpanel" id={`agent-panel-${activeTab}`} aria-labelledby={`agent-tab-${activeTab}`} tabIndex={0}>
        {panels[activeTab]}
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <Button variant="primary" onClick={() => void handleSave()} loading={saving}>
          Salvar
        </Button>
      </div>
    </div>
  );
}
