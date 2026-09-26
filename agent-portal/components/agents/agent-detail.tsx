"use client";

import * as React from "react";
import { Plus, X, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Toggle } from "@/components/ui/toggle";
import { Card } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import type {
  Agent,
  PortDef,
  SkillRef,
  ToolRef,
  MCPServerRef,
  KnowledgeRef,
  IntegrationRef,
  FlowAction,
  Skill,
  CustomTool,
  MCPServer,
  KnowledgeBase,
  NotificationChannel,
} from "@/lib/types";
import type { AgentUpdatePayload } from "@/lib/agents";

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
   * A página de edição incrementa esta key a cada config_update do chat
   * (spec §10) para o formulário refletir o draft sem perder a identidade
   * dos campos (React remonta o subtree quando a key muda).
   */
  resetKey?: string | number;
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

export function AgentDetail({
  agent,
  options,
  onSave,
  saving = false,
}: AgentDetailProps) {
  const { addToast } = useToast();

  const [name, setName] = React.useState(agent?.name ?? "");
  const [type, setType] = React.useState(agent?.type ?? "custom");
  const [description, setDescription] = React.useState(agent?.description ?? "");
  const [prompt, setPrompt] = React.useState(agent?.prompt ?? "");
  const [strategy, setStrategy] = React.useState(agent?.strategy ?? "");
  const [model, setModel] = React.useState(agent?.model ?? "gpt-4o");
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

  // Seletores de mochila (valor do select).
  const [skillSel, setSkillSel] = React.useState("");
  const [toolSel, setToolSel] = React.useState("");
  const [mcpSel, setMcpSel] = React.useState("");
  const [knowledgeSel, setKnowledgeSel] = React.useState("");
  const [integrationSel, setIntegrationSel] = React.useState("");

  const [nameError, setNameError] = React.useState<string | undefined>();

  // Sincroniza o formulário quando a prop `agent` muda (config_update do
  // chat via resetKey, spec §10). Mantém a identidade dos campos via
  // useState inicial + chave de remonte no nível da página.
  React.useEffect(() => {
    if (!agent) return;
    setName(agent.name);
    setType(agent.type);
    setDescription(agent.description);
    setPrompt(agent.prompt);
    setStrategy(agent.strategy);
    setModel(agent.model);
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

  const addPort = (
    setter: React.Dispatch<React.SetStateAction<PortDef[]>>,
    list: PortDef[]
  ) => {
    setter([
      ...list,
      { name: "", type: "string", required: false },
    ]);
  };

  const updatePort = (
    setter: React.Dispatch<React.SetStateAction<PortDef[]>>,
    index: number,
    patch: Partial<PortDef>
  ) => {
    setter((prev) =>
      prev.map((p, i) => (i === index ? { ...p, ...patch } : p))
    );
  };

  const removePort = (
    setter: React.Dispatch<React.SetStateAction<PortDef[]>>,
    index: number
  ) => {
    setter((prev) => prev.filter((_, i) => i !== index));
  };

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

    try {
      await onSave(payload);
    } catch (e) {
      addToast(
        "error",
        e instanceof Error ? e.message : "Falha ao salvar o agente."
      );
    }
  };

  return (
    <div
      data-agent-detail
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
        gap: "16px",
        alignItems: "start",
      }}
    >
      {/* Coluna esquerda: identidade + contrato */}
      <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
        <Card>
          <SectionTitle>Identidade</SectionTitle>
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            <Input
              label="Nome"
              value={name}
              onChange={(e) => setName(e.target.value)}
              error={nameError}
              placeholder="Ex.: Backend Developer"
            />
            <Input
              label="Tipo"
              value={type}
              onChange={(e) => setType(e.target.value)}
              placeholder="Ex.: Developer"
            />
            <Textarea
              label="Descrição"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="O que este agente faz?"
            />
            <Textarea
              label="Prompt"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={4}
              placeholder="Instruções do sistema para o agente"
            />
            <Textarea
              label="Strategy"
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              rows={2}
              placeholder="Estratégia de execução"
            />
          </div>
        </Card>

        <Card>
          <SectionTitle>Contrato de Fluxo</SectionTitle>
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            {/* Inputs */}
            <div>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: "8px",
                }}
              >
                <span style={{ fontSize: "12px", fontWeight: 500, color: "var(--text)" }}>
                  Entradas
                </span>
                <Button
                  size="sm"
                  onClick={() => addPort(setInputs, inputs)}
                  aria-label="Adicionar entrada"
                >
                  <Plus size={12} aria-hidden="true" />
                  Adicionar
                </Button>
              </div>
              {inputs.length === 0 && (
                <p style={{ fontSize: "12px", color: "var(--text-muted)", margin: 0 }}>
                  Nenhuma entrada definida.
                </p>
              )}
              {inputs.map((port, i) => (
                <div
                  key={i}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 110px auto auto",
                    gap: "6px",
                    alignItems: "center",
                    marginBottom: "6px",
                  }}
                >
                  <input
                    aria-label={`Nome da entrada ${i + 1}`}
                    value={port.name}
                    onChange={(e) => updatePort(setInputs, i, { name: e.target.value })}
                    placeholder="nome"
                    style={{
                      padding: "6px 10px",
                      borderRadius: "var(--radius-sm)",
                      border: "1px solid var(--border)",
                      background: "var(--bg-elevated)",
                      color: "var(--text)",
                      fontSize: "12px",
                      outline: "none",
                    }}
                  />
                  <select
                    aria-label={`Tipo da entrada ${i + 1}`}
                    value={port.type}
                    onChange={(e) => updatePort(setInputs, i, { type: e.target.value })}
                    style={{
                      padding: "6px 8px",
                      borderRadius: "var(--radius-sm)",
                      border: "1px solid var(--border)",
                      background: "var(--bg-elevated)",
                      color: "var(--text)",
                      fontSize: "12px",
                      outline: "none",
                    }}
                  >
                    {["string", "number", "boolean", "object", "array"].map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                  <label
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "4px",
                      fontSize: "11px",
                      color: "var(--text-secondary)",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={port.required}
                      onChange={(e) =>
                        updatePort(setInputs, i, { required: e.target.checked })
                      }
                      aria-label={`Entrada ${i + 1} obrigatória`}
                    />
                    req
                  </label>
                  <button
                    type="button"
                    onClick={() => removePort(setInputs, i)}
                    aria-label={`Remover entrada ${i + 1}`}
                    style={{
                      background: "none",
                      border: "none",
                      color: "var(--text-muted)",
                      cursor: "pointer",
                      padding: 2,
                      display: "flex",
                    }}
                  >
                    <Trash2 size={13} aria-hidden="true" />
                  </button>
                </div>
              ))}
            </div>

            {/* Outputs */}
            <div>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: "8px",
                }}
              >
                <span style={{ fontSize: "12px", fontWeight: 500, color: "var(--text)" }}>
                  Saídas
                </span>
                <Button
                  size="sm"
                  onClick={() => addPort(setOutputs, outputs)}
                  aria-label="Adicionar saída"
                >
                  <Plus size={12} aria-hidden="true" />
                  Adicionar
                </Button>
              </div>
              {outputs.length === 0 && (
                <p style={{ fontSize: "12px", color: "var(--text-muted)", margin: 0 }}>
                  Nenhuma saída definida.
                </p>
              )}
              {outputs.map((port, i) => (
                <div
                  key={i}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 110px auto auto",
                    gap: "6px",
                    alignItems: "center",
                    marginBottom: "6px",
                  }}
                >
                  <input
                    aria-label={`Nome da saída ${i + 1}`}
                    value={port.name}
                    onChange={(e) => updatePort(setOutputs, i, { name: e.target.value })}
                    placeholder="nome"
                    style={{
                      padding: "6px 10px",
                      borderRadius: "var(--radius-sm)",
                      border: "1px solid var(--border)",
                      background: "var(--bg-elevated)",
                      color: "var(--text)",
                      fontSize: "12px",
                      outline: "none",
                    }}
                  />
                  <select
                    aria-label={`Tipo da saída ${i + 1}`}
                    value={port.type}
                    onChange={(e) => updatePort(setOutputs, i, { type: e.target.value })}
                    style={{
                      padding: "6px 8px",
                      borderRadius: "var(--radius-sm)",
                      border: "1px solid var(--border)",
                      background: "var(--bg-elevated)",
                      color: "var(--text)",
                      fontSize: "12px",
                      outline: "none",
                    }}
                  >
                    {["string", "number", "boolean", "object", "array"].map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                  <label
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "4px",
                      fontSize: "11px",
                      color: "var(--text-secondary)",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={port.required}
                      onChange={(e) =>
                        updatePort(setOutputs, i, { required: e.target.checked })
                      }
                      aria-label={`Saída ${i + 1} obrigatória`}
                    />
                    req
                  </label>
                  <button
                    type="button"
                    onClick={() => removePort(setOutputs, i)}
                    aria-label={`Remover saída ${i + 1}`}
                    style={{
                      background: "none",
                      border: "none",
                      color: "var(--text-muted)",
                      cursor: "pointer",
                      padding: 2,
                      display: "flex",
                    }}
                  >
                    <Trash2 size={13} aria-hidden="true" />
                  </button>
                </div>
              ))}
            </div>

            {/* Actions */}
            <div>
              <span
                style={{
                  fontSize: "12px",
                  fontWeight: 500,
                  color: "var(--text)",
                  display: "block",
                  marginBottom: "8px",
                }}
              >
                Ações
              </span>
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
                        padding: "6px 12px",
                        borderRadius: "var(--radius-sm)",
                        border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
                        background: active ? "var(--accent-subtle)" : "var(--bg-card)",
                        color: active ? "var(--accent)" : "var(--text-secondary)",
                        fontSize: "12px",
                        fontWeight: 500,
                        cursor: "pointer",
                        transition: "all var(--transition)",
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
      </div>

      {/* Coluna direita: execução + mochila */}
      <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
        <Card>
          <SectionTitle>Execução</SectionTitle>
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            <Input
              label="Modelo"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="Ex.: gpt-4o"
            />
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "12px",
              }}
            >
              <Input
                label="Max iterações"
                type="number"
                min={1}
                max={1000}
                value={maxIterations}
                onChange={(e) => setMaxIterations(e.target.value)}
              />
              <Input
                label="Timeout (s)"
                type="number"
                min={1}
                max={3600}
                value={timeout}
                onChange={(e) => setTimeout_(e.target.value)}
              />
            </div>
            <Select
              label="Canal de aprovação"
              value={approvalChannel}
              onValueChange={(v) => setApprovalChannel(v as NotificationChannel)}
              options={APPROVAL_CHANNELS}
            />
            <Toggle
              label="Acesso a shell"
              description="Permite ao agente executar comandos no shell."
              checked={shellAccess}
              onChange={setShellAccess}
            />
          </div>
        </Card>

        <Card>
          <SectionTitle>Mochila</SectionTitle>
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            {/* Skills */}
            <div>
              <span
                style={{
                  fontSize: "12px",
                  fontWeight: 500,
                  color: "var(--text)",
                  display: "block",
                  marginBottom: "6px",
                }}
              >
                Skills
              </span>
              <div style={{ display: "flex", gap: "6px", marginBottom: "8px" }}>
                <Select
                  aria-label="Selecionar skill"
                  value={skillSel}
                  onValueChange={setSkillSel}
                  options={skillOptions}
                  placeholder={
                    options.skills.length
                      ? "Escolher skill…"
                      : "Nenhuma skill cadastrada"
                  }
                />
                <Button
                  size="sm"
                  onClick={addSkill}
                  disabled={!skillSel}
                  aria-label="Adicionar skill"
                >
                  <Plus size={12} aria-hidden="true" />
                </Button>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                {skills.length === 0 && (
                  <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                    Nenhuma skill associada.
                  </span>
                )}
                {skills.map((s) => (
                  <Chip
                    key={s.skillId}
                    label={s.skillId}
                    onRemove={() =>
                      setSkills((prev) => prev.filter((x) => x.skillId !== s.skillId))
                    }
                  />
                ))}
              </div>
            </div>

            {/* Tools */}
            <div>
              <span
                style={{
                  fontSize: "12px",
                  fontWeight: 500,
                  color: "var(--text)",
                  display: "block",
                  marginBottom: "6px",
                }}
              >
                Tools Custom
              </span>
              <div style={{ display: "flex", gap: "6px", marginBottom: "8px" }}>
                <Select
                  aria-label="Selecionar tool"
                  value={toolSel}
                  onValueChange={setToolSel}
                  options={toolOptions}
                  placeholder={
                    options.tools.length
                      ? "Escolher tool…"
                      : "Nenhuma tool cadastrada"
                  }
                />
                <Button
                  size="sm"
                  onClick={addTool}
                  disabled={!toolSel}
                  aria-label="Adicionar tool"
                >
                  <Plus size={12} aria-hidden="true" />
                </Button>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                {tools.length === 0 && (
                  <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                    Nenhuma tool associada.
                  </span>
                )}
                {tools.map((t) => (
                  <Chip
                    key={t.toolId}
                    label={t.toolId}
                    onRemove={() =>
                      setTools((prev) => prev.filter((x) => x.toolId !== t.toolId))
                    }
                  />
                ))}
              </div>
            </div>

            {/* MCP */}
            <div>
              <span
                style={{
                  fontSize: "12px",
                  fontWeight: 500,
                  color: "var(--text)",
                  display: "block",
                  marginBottom: "6px",
                }}
              >
                Servidores MCP
              </span>
              <div style={{ display: "flex", gap: "6px", marginBottom: "8px" }}>
                <Select
                  aria-label="Selecionar servidor MCP"
                  value={mcpSel}
                  onValueChange={setMcpSel}
                  options={mcpOptions}
                  placeholder={
                    options.mcpServers.length
                      ? "Escolher servidor…"
                      : "Nenhum servidor cadastrado"
                  }
                />
                <Button
                  size="sm"
                  onClick={addMcp}
                  disabled={!mcpSel}
                  aria-label="Adicionar servidor MCP"
                >
                  <Plus size={12} aria-hidden="true" />
                </Button>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                {mcpServers.length === 0 && (
                  <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                    Nenhum servidor MCP associado.
                  </span>
                )}
                {mcpServers.map((m) => (
                  <Chip
                    key={m.serverId}
                    label={m.serverId}
                    onRemove={() =>
                      setMcpServers((prev) =>
                        prev.filter((x) => x.serverId !== m.serverId)
                      )
                    }
                  />
                ))}
              </div>
            </div>

            {/* Knowledge */}
            <div>
              <span
                style={{
                  fontSize: "12px",
                  fontWeight: 500,
                  color: "var(--text)",
                  display: "block",
                  marginBottom: "6px",
                }}
              >
                Knowledge
              </span>
              <div style={{ display: "flex", gap: "6px", marginBottom: "8px" }}>
                <Select
                  aria-label="Selecionar base de conhecimento"
                  value={knowledgeSel}
                  onValueChange={setKnowledgeSel}
                  options={knowledgeOptions}
                  placeholder={
                    options.knowledge.length
                      ? "Escolher base…"
                      : "Nenhuma base cadastrada"
                  }
                />
                <Button
                  size="sm"
                  onClick={addKnowledge}
                  disabled={!knowledgeSel}
                  aria-label="Adicionar base de conhecimento"
                >
                  <Plus size={12} aria-hidden="true" />
                </Button>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                {knowledge.length === 0 && (
                  <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                    Nenhuma base de conhecimento associada.
                  </span>
                )}
                {knowledge.map((k) => (
                  <Chip
                    key={k.reference}
                    label={k.reference}
                    onRemove={() =>
                      setKnowledge((prev) =>
                        prev.filter((x) => x.reference !== k.reference)
                      )
                    }
                  />
                ))}
              </div>
            </div>

            {/* Integrações */}
            <div>
              <span
                style={{
                  fontSize: "12px",
                  fontWeight: 500,
                  color: "var(--text)",
                  display: "block",
                  marginBottom: "6px",
                }}
              >
                Integrações
              </span>
              <div style={{ display: "flex", gap: "6px", marginBottom: "8px" }}>
                <Select
                  aria-label="Selecionar integração"
                  value={integrationSel}
                  onValueChange={setIntegrationSel}
                  options={INTEGRATION_PLATFORMS.map((p) => ({
                    value: p,
                    label: p,
                  }))}
                  placeholder="Escolher plataforma…"
                />
                <Button
                  size="sm"
                  onClick={addIntegration}
                  disabled={!integrationSel}
                  aria-label="Adicionar integração"
                >
                  <Plus size={12} aria-hidden="true" />
                </Button>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                {integrations.length === 0 && (
                  <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                    Nenhuma integração associada.
                  </span>
                )}
                {integrations.map((integ) => (
                  <Chip
                    key={integ.platform}
                    label={integ.platform}
                    onRemove={() =>
                      setIntegrations((prev) =>
                        prev.filter((x) => x.platform !== integ.platform)
                      )
                    }
                  />
                ))}
              </div>
            </div>
          </div>
        </Card>

        {/* Salvar */}
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <Button variant="primary" onClick={() => void handleSave()} loading={saving}>
            Salvar
          </Button>
        </div>
      </div>
    </div>
  );
}
