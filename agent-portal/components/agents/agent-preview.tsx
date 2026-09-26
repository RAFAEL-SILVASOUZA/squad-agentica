"use client";

import * as React from "react";
import {
  Bot,
  Cpu,
  ListChecks,
  Wrench,
  Server,
  BookOpen,
  Plug,
  ArrowDown,
  ArrowUp,
  Zap,
  Shield,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import type { LucideIcon } from "lucide-react";
import type {
  Agent,
  PortDef,
  SkillRef,
  ToolRef,
  MCPServerRef,
  KnowledgeRef,
  IntegrationRef,
  FlowAction,
} from "@/lib/types";

/**
 * Preview do agente (spec §10.1): resumo do draft atualizado a cada
 * resposta do chat (evento config_update).
 *
 * Mostra identidade, mochila (skills, tools, MCP, knowledge, integrações),
 * contrato de fluxo (inputs, outputs, actions) e execução (modelo, limites,
 * shellAccess).
 *
 * Sem emojis; ícones via lucide-react.
 */

export interface AgentPreviewProps {
  /** Configuração parcial do draft (o que o chat já preencheu). */
  config: Partial<Agent>;
  /** true enquanto o assistente está respondendo. */
  streaming?: boolean;
}

const ACTION_LABEL: Record<FlowAction, string> = {
  follow: "seguir",
  return: "devolver",
  finalize: "finalizar",
};

function portsLabel(ports: PortDef[]): string {
  return ports.map((p) => p.name).join(", ");
}

function SectionTitle({
  icon: Icon,
  children,
}: {
  icon: LucideIcon;
  children: React.ReactNode;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "6px",
        fontSize: "11px",
        fontWeight: 600,
        color: "var(--text-secondary)",
        textTransform: "uppercase",
        letterSpacing: "0.5px",
        margin: "0 0 8px",
      }}
    >
      <Icon size={13} aria-hidden="true" />
      {children}
    </div>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        fontSize: "11px",
        color: "var(--text)",
        background: "var(--bg-hover)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "10px",
        padding: "2px 8px",
      }}
    >
      {children}
    </span>
  );
}

function Item({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        gap: "12px",
        padding: "4px 0",
        fontSize: "12px",
      }}
    >
      <span style={{ color: "var(--text-secondary)" }}>{label}</span>
      <span
        style={{
          color: "var(--text)",
          textAlign: "right",
          fontWeight: 500,
          wordBreak: "break-word",
        }}
      >
        {value}
      </span>
    </div>
  );
}

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: LucideIcon;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ padding: "12px 0", borderBottom: "1px solid var(--border)" }}>
      <SectionTitle icon={Icon}>{title}</SectionTitle>
      {children}
    </div>
  );
}

export function AgentPreview({ config, streaming = false }: AgentPreviewProps) {
  const hasAny =
    config.name ||
    config.type ||
    config.description ||
    config.model ||
    (config.skills && config.skills.length > 0) ||
    (config.tools && config.tools.length > 0) ||
    (config.mcpServers && config.mcpServers.length > 0) ||
    (config.knowledge && config.knowledge.length > 0) ||
    (config.integrations && config.integrations.length > 0) ||
    (config.inputs && config.inputs.length > 0) ||
    (config.outputs && config.outputs.length > 0) ||
    (config.actions && config.actions.length > 0);

  if (!hasAny) {
    return (
      <Card>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: "8px",
            padding: "24px 12px",
            textAlign: "center",
          }}
        >
          <Bot size={28} aria-hidden="true" style={{ color: "var(--text-muted)" }} />
          <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
            {streaming
              ? "Gerando configuração…"
              : "Descreva o agente no chat para ver o preview aqui."}
          </span>
        </div>
      </Card>
    );
  }

  const skills: SkillRef[] = config.skills ?? [];
  const tools: ToolRef[] = config.tools ?? [];
  const mcpServers: MCPServerRef[] = config.mcpServers ?? [];
  const knowledge: KnowledgeRef[] = config.knowledge ?? [];
  const integrations: IntegrationRef[] = config.integrations ?? [];
  const inputs: PortDef[] = config.inputs ?? [];
  const outputs: PortDef[] = config.outputs ?? [];
  const actions: FlowAction[] = config.actions ?? [];

  return (
    <Card>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          marginBottom: "4px",
        }}
      >
        <span
          aria-hidden="true"
          style={{
            width: 28,
            height: 28,
            borderRadius: "var(--radius-sm)",
            background: "var(--accent-subtle)",
            color: "var(--accent)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <Bot size={15} aria-hidden="true" />
        </span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div
            style={{
              fontSize: "14px",
              fontWeight: 600,
              color: "var(--text)",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {config.name || "Sem nome"}
          </div>
          {config.type && (
            <div style={{ fontSize: "11px", color: "var(--text-secondary)" }}>
              {config.type}
            </div>
          )}
        </div>
      </div>

      {config.description && (
        <p
          style={{
            fontSize: "12px",
            color: "var(--text-secondary)",
            margin: "8px 0 0",
            lineHeight: 1.5,
          }}
        >
          {config.description}
        </p>
      )}

      {/* Identidade / execução */}
      {(config.model || config.maxIterations !== undefined || config.timeout !== undefined) && (
        <Section icon={Cpu} title="Execução">
          {config.model && <Item label="Modelo" value={config.model} />}
          {config.maxIterations !== undefined && (
            <Item label="Max iterações" value={config.maxIterations} />
          )}
          {config.timeout !== undefined && (
            <Item label="Timeout" value={`${config.timeout}s`} />
          )}
          {config.shellAccess !== undefined && (
            <Item
              label="Acesso a shell"
              value={
                <span style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
                  <Shield size={12} aria-hidden="true" />
                  {config.shellAccess ? "Ativado" : "Desativado"}
                </span>
              }
            />
          )}
        </Section>
      )}

      {/* Mochila */}
      {(skills.length > 0 ||
        tools.length > 0 ||
        mcpServers.length > 0 ||
        knowledge.length > 0 ||
        integrations.length > 0) && (
        <Section icon={Wrench} title="Mochila">
          {skills.length > 0 && (
            <div style={{ marginBottom: "8px" }}>
              <div style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "4px" }}>
                Skills
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                {skills.map((s, i) => (
                  <Chip key={`${s.skillId}-${i}`}>{s.skillId}</Chip>
                ))}
              </div>
            </div>
          )}
          {tools.length > 0 && (
            <div style={{ marginBottom: "8px" }}>
              <div style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "4px" }}>
                Tools
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                {tools.map((t, i) => (
                  <Chip key={`${t.toolId}-${i}`}>{t.toolId}</Chip>
                ))}
              </div>
            </div>
          )}
          {mcpServers.length > 0 && (
            <div style={{ marginBottom: "8px" }}>
              <div style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "4px" }}>
                Servidores MCP
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                {mcpServers.map((m, i) => (
                  <Chip key={`${m.serverId}-${i}`}>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
                      <Server size={11} aria-hidden="true" />
                      {m.serverId}
                    </span>
                  </Chip>
                ))}
              </div>
            </div>
          )}
          {knowledge.length > 0 && (
            <div style={{ marginBottom: "8px" }}>
              <div style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "4px" }}>
                Knowledge
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                {knowledge.map((k, i) => (
                  <Chip key={`${k.reference}-${i}`}>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
                      <BookOpen size={11} aria-hidden="true" />
                      {k.reference}
                    </span>
                  </Chip>
                ))}
              </div>
            </div>
          )}
          {integrations.length > 0 && (
            <div>
              <div style={{ fontSize: "11px", color: "var(--text-muted)", marginBottom: "4px" }}>
                Integrações
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                {integrations.map((integ, i) => (
                  <Chip key={`${integ.platform}-${i}`}>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
                      <Plug size={11} aria-hidden="true" />
                      {integ.platform}
                    </span>
                  </Chip>
                ))}
              </div>
            </div>
          )}
        </Section>
      )}

      {/* Contrato de fluxo */}
      {(inputs.length > 0 || outputs.length > 0 || actions.length > 0) && (
        <Section icon={ListChecks} title="Contrato de Fluxo">
          {inputs.length > 0 && (
            <Item
              label="Entrada"
              value={
                <span style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
                  <ArrowDown size={12} aria-hidden="true" />
                  {portsLabel(inputs)}
                </span>
              }
            />
          )}
          {outputs.length > 0 && (
            <Item
              label="Saída"
              value={
                <span style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
                  <ArrowUp size={12} aria-hidden="true" />
                  {portsLabel(outputs)}
                </span>
              }
            />
          )}
          {actions.length > 0 && (
            <Item
              label="Ações"
              value={
                <span style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
                  <Zap size={12} aria-hidden="true" />
                  {actions.map((a) => ACTION_LABEL[a] ?? a).join(" · ")}
                </span>
              }
            />
          )}
        </Section>
      )}
    </Card>
  );
}
