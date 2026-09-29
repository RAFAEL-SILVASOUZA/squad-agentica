"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, CheckCircle2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorPanel } from "@/components/ui/error-panel";
import { useToast } from "@/components/ui/toast";
import { AgentChat, AgentPreview } from "@/components/agents";
import type { AgentValidationState } from "@/components/agents/agent-preview";
import { api, ApiError } from "@/lib/api";
import { confirmAgentDraft, restoreAgentDraft } from "@/lib/agent-chat";

/** Chave do draftId no sessionStorage (retomada da tela, Task 3). */
const DRAFT_SESSION_KEY = "agent-draft-id";

interface SaveError {
  message: string;
  detail: string;
  /** 404 draft_not_found: o rascunho expirou no servidor. */
  draftExpired: boolean;
}
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
 * - Task 3: o draftId é persistido em sessionStorage (agent-draft-id) e o
 *   draft é retomado ao montar; o preview valida a config em tempo real
 *   (POST /api/agents/validate, debounce 500 ms); o Salvar é desabilitado
 *   enquanto valid=false. Em 404 draft_not_found o ErrorPanel oferece
 *   "Recriar a partir do que está na tela" (restore + confirm).
 *
 * Portal nasce vazio (contrato §0): sem seed ilustrativo.
 * Estados: loading (skeleton da mochila), erro (ErrorPanel + retry).
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

  // draftId retomado do sessionStorage (Task 3): sobrevive ao reload da tela
  // enquanto o draft existir no servidor (TTL 24h).
  const [draftId, setDraftId] = React.useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    return window.sessionStorage.getItem(DRAFT_SESSION_KEY);
  });
  const [config, setConfig] = React.useState<Partial<Agent>>({});
  const [saving, setSaving] = React.useState(false);
  const [restoring, setRestoring] = React.useState(false);
  const [saveError, setSaveError] = React.useState<SaveError | null>(null);
  const [validation, setValidation] = React.useState<AgentValidationState | null>(null);
  const [streaming, setStreaming] = React.useState(false);
  const [options, setOptions] = React.useState<BackpackOptions | null>(null);
  const [optionsError, setOptionsError] = React.useState(false);

  // Persiste o draftId em sessionStorage (Task 3).
  const handleDraftId = React.useCallback((id: string) => {
    setDraftId(id);
    try {
      window.sessionStorage.setItem(DRAFT_SESSION_KEY, id);
    } catch {
      // Sem sessionStorage (modo privado) o fluxo continua sem retomada.
    }
  }, []);

  // O preview valida a config com debounce de 500 ms (Task 3).
  const handleValidate = React.useCallback((state: AgentValidationState) => {
    setValidation(state);
  }, []);

  const handleStreamingChange = React.useCallback((isStreaming: boolean) => {
    setStreaming(isStreaming);
  }, []);

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

  // Task 3: validação do preview controla o botão Salvar (valid=false →
  // desabilitado). Sem draft ainda, o botão já está desabilitado por draftId.
  const saveBlocked = validation !== null && !validation.valid;

  const doConfirm = React.useCallback(
    async (id: string) => {
      setSaving(true);
      try {
        const agent = await confirmAgentDraft(id);
        try {
          window.sessionStorage.removeItem(DRAFT_SESSION_KEY);
        } catch {
          // sem sessionStorage: ignora.
        }
        addToast("success", `Agente "${agent.name}" criado.`);
        router.push(`/agents/${agent.id}`);
      } catch (e) {
        // Task 3: o erro do confirm carrega status + code do envelope
        // (confirmAgentDraft em lib/agent-chat.ts). 404 + code
        // "draft_not_found" significa que o rascunho expirou no servidor.
        const er = e as (Error & { status?: number; code?: string }) | null;
        const draftExpired =
          er !== null && er.status === 404 && er.code === "draft_not_found";
        const detail =
          e instanceof ApiError ? e.describe() : "";
        setSaveError({
          message: er instanceof Error ? er.message : "Falha ao salvar o agente.",
          detail,
          draftExpired,
        });
        setSaving(false);
      }
    },
    [addToast, router]
  );

  const handleSave = React.useCallback(async () => {
    if (!draftId || restoring) return;
    setSaveError(null);
    await doConfirm(draftId);
  }, [draftId, restoring, doConfirm]);

  // Recuperação do draft expirado (404 draft_not_found): recria o rascunho
  // a partir da config que ainda está na tela e confirma em seguida.
  const handleRestoreAndConfirm = React.useCallback(async () => {
    setRestoring(true);
    setSaveError(null);
    try {
      const restored = await restoreAgentDraft(config as Record<string, unknown>);
      handleDraftId(restored.draftId);
      await doConfirm(restored.draftId);
    } catch (e) {
      setSaveError({
        message: e instanceof Error ? e.message : "Falha ao recriar o rascunho.",
        detail: e instanceof ApiError ? e.describe() : "",
        draftExpired: false,
      });
    } finally {
      setRestoring(false);
    }
  }, [config, doConfirm, handleDraftId]);

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
          loading={saving || restoring}
          // E2: sem draft utilizável (nome no config), salvar é inútil: o
          // backend recusa (400 incomplete_draft). Task 3: o botão também
          // desabilita enquanto a validação do preview diz valid=false.
          disabled={!draftId || saveBlocked || saving}
        >
          <CheckCircle2 size={14} aria-hidden="true" />
          Salvar agente
        </Button>
      </div>

      {/* Erro de salvamento (Task 3): inline com recuperação */}
      {saveError && (
        <div style={{ marginBottom: "16px" }}>
          <ErrorPanel
            title={
              saveError.draftExpired
                ? "O rascunho expirou no servidor"
                : `Não foi possível salvar o agente: ${saveError.message}`
            }
            detail={saveError.detail || undefined}
            onRetry={
              saveError.draftExpired ? handleRestoreAndConfirm : () => void handleSave()
            }
            retryLabel={saveError.draftExpired ? "Recriar a partir do que está na tela" : "Tentar de novo"}
          />
        </div>
      )}

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
          onDraftId={handleDraftId}
          onConfigUpdate={handleConfigUpdate}
          onStreamingChange={handleStreamingChange}
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
          <AgentPreview config={config} streaming={streaming} onValidate={handleValidate} />
          {!draftId && (
            <EmptyState
              title="Ainda sem rascunho"
              description="Envie uma mensagem no chat para o assistente gerar o rascunho do agente. O botão Salvar habilita após o primeiro rascunho."
            />
          )}
        </div>
      </div>
    </div>
  );
}
