"use client";

import * as React from "react";
import { Plus, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Integration, LlmProviderKind, LlmConnectionTestResult } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Modal } from "@/components/ui/modal";
import { ErrorPanel } from "@/components/ui/error-panel";

const PROVIDER_KINDS: { value: LlmProviderKind; label: string }[] = [
  { value: "openai", label: "OpenAI" },
  { value: "openai_compatible", label: "OpenAI compatível (LM Studio, Ollama, vLLM…)" },
  { value: "mock", label: "Mock (desenvolvimento, sem rede)" },
];

/** Lê um valor do config de uma integração LLM como string. */
function strOf(config: Record<string, unknown> | undefined, key: string): string {
  const v = config?.[key];
  return typeof v === "string" ? v : "";
}

/**
 * Formulário de criação/edição de conexão LLM (adendo 8).
 *
 * - provider_kind, base_url, api_key (password), models (lista), embeddings (opcional).
 * - A chave é enviada em claro no create/update; a API a sela (Fernet) e devolve
 *   só o hint (últimos 4). Ao editar, deixar a chave vazia mantém a atual.
 * - "Testar conexão" chama POST /api/integrations/llm/test (não persiste, não ecoa a chave).
 */
export function LlmConnectionForm({ connection, onClose, onSaved }: {
  connection?: Integration;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = React.useState(connection?.name ?? "");
  const [providerKind, setProviderKind] = React.useState<LlmProviderKind>(
    (connection?.config.provider_kind as LlmProviderKind) ?? "openai"
  );
  const [baseUrl, setBaseUrl] = React.useState(strOf(connection?.config, "base_url"));
  const [apiKey, setApiKey] = React.useState("");
  const [models, setModels] = React.useState<string[]>(
    Array.isArray(connection?.config.models)
      ? connection.config.models.map((m) => String(m)).filter(Boolean)
      : []
  );
  const [modelDraft, setModelDraft] = React.useState("");
  const [embeddings, setEmbeddings] = React.useState(strOf(connection?.config, "embedding_model"));
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [testBusy, setTestBusy] = React.useState(false);
  const [testResult, setTestResult] = React.useState<{ ok: boolean; message: string } | null>(null);
  const [saveError, setSaveError] = React.useState<{ message: string; detail?: string } | null>(null);

  const isMock = providerKind === "mock";

  function addModel() {
    const value = modelDraft.trim();
    if (!value || models.includes(value)) return;
    setModels((prev) => [...prev, value]);
    setModelDraft("");
  }

  function removeModel(model: string) {
    setModels((prev) => prev.filter((m) => m !== model));
  }

  /** Monta o config de teste (não persiste). Usa o 1º modelo como alvo. */
  function buildTestConfig() {
    const config: Record<string, unknown> = {
      provider_kind: providerKind,
      base_url: baseUrl.trim(),
      model: models[0] ?? "",
    };
    // O endpoint de teste lê a chave em claro do config (não resolve a chave
    // criptografada salva), então só enviamos a chave quando foi digitada.
    if (!isMock && apiKey.trim()) config.api_key = apiKey.trim();
    if (embeddings.trim()) config.embedding = { model: embeddings.trim() };
    return config;
  }

  async function testConnection() {
    if (testBusy) return;
    if (!isMock && !apiKey.trim()) {
      setError("Digite a chave de API para testar.");
      return;
    }
    setTestBusy(true);
    setTestResult(null);
    setError("");
    try {
      const result = await api.post<LlmConnectionTestResult>("/api/integrations/llm/test", {
        type: "llm",
        config: buildTestConfig(),
      });
      if (result.ok) {
        const parts = [result.model ? `modelo ${result.model}` : null, result.embeddingDim ? `embeddings ${result.embeddingDim}d` : null].filter(Boolean);
        setTestResult({ ok: true, message: `Conectado${parts.length ? ` (${parts.join(", ")})` : ""}${result.latencyMs != null ? ` · ${result.latencyMs} ms` : ""}` });
      } else {
        setTestResult({ ok: false, message: result.error || "Falha ao testar a conexão." });
      }
    } catch (e) {
      setTestResult({ ok: false, message: e instanceof ApiError ? e.message : "Não foi possível testar a conexão." });
    } finally {
      setTestBusy(false);
    }
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (!name.trim()) {
      setError("Informe um nome para a conexão.");
      return;
    }
    if (!isMock && !apiKey.trim() && !connection) {
      setError("Digite a chave de API.");
      return;
    }
    setBusy(true);
    setError("");
    setSaveError(null);

    const config: Record<string, unknown> = {
      provider_kind: providerKind,
      base_url: baseUrl.trim(),
      models,
    };
    if (models.length) config.default_model = models[0];
    if (!isMock) config.api_key = apiKey.trim() || (connection ? "***" : "");
    if (embeddings.trim()) config.embedding_model = embeddings.trim();

    try {
      if (connection) await api.put(`/api/integrations/${connection.id}`, { name: name.trim(), config });
      else await api.post("/api/integrations", { type: "llm", name: name.trim(), config });
      setApiKey("");
      onSaved();
    } catch (e) {
      setSaveError({
        message: "Não foi possível salvar a conexão",
        detail: e instanceof ApiError ? e.describe() : undefined,
      });
    } finally {
      setBusy(false);
    }
  }

  return <Modal open onClose={() => { if (!busy) onClose(); }} title={connection ? "Editar conexão LLM" : "Nova conexão LLM"} size="lg">
    <form onSubmit={(event) => void save(event)} style={{ display: "grid", gap: 16 }}>
      <Input label="Nome" value={name} onChange={(e) => setName(e.target.value)} required maxLength={200} disabled={busy} placeholder="Ex.: OpenAI principal" />
      <Select label="Provedor" value={providerKind} onValueChange={(v) => setProviderKind(v as LlmProviderKind)} options={PROVIDER_KINDS} disabled={busy} />
      <Input label="Base URL" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} disabled={busy || isMock} placeholder="Ex.: http://localhost:11434/v1" hint={isMock ? "O mock não usa base URL." : "Opcional para OpenAI; obrigatório para servidores compatíveis."} />
      <Input label="Chave de API" type="password" autoComplete="new-password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} required={!connection && !isMock} disabled={busy || isMock}
        hint={isMock ? "O mock não usa chave." : `${connection ? "Deixe vazio para manter a chave atual." : ""} A chave fica criptografada e nunca é mostrada de novo.`} />
      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
        <span style={{ fontSize: "13px", fontWeight: 500, color: "var(--text)" }}>Modelos</span>
        <div style={{ display: "flex", gap: "6px" }}>
          <Input aria-label="Modelo" value={modelDraft} onChange={(e) => setModelDraft(e.target.value)} placeholder="Ex.: gpt-4o-mini" disabled={busy}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addModel(); } }} />
          <Button type="button" size="sm" onClick={addModel} disabled={busy || !modelDraft.trim()} aria-label="Adicionar modelo"><Plus size={12} aria-hidden="true" /></Button>
        </div>
        {models.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "4px", alignItems: "center" }}>
            {models.map((m) => (
              <span key={m} style={{ display: "inline-flex", alignItems: "center", gap: "4px", fontSize: "11px", color: "var(--text)", background: "var(--bg-hover)", border: "1px solid var(--border-subtle)", borderRadius: "10px", padding: "2px 8px" }}>
                {m}
                <button type="button" onClick={() => removeModel(m)} aria-label={`Remover ${m}`} style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", padding: 0, display: "flex", alignItems: "center" }}>
                  <X size={11} aria-hidden="true" />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>
      <Input label="Modelo de embeddings" value={embeddings} onChange={(e) => setEmbeddings(e.target.value)} disabled={busy} placeholder="Opcional. Ex.: text-embedding-3-small" hint="Opcional. Usado para bases de conhecimento com esta conexão." />
      {error && <p role="alert" style={{ color: "var(--error)" }}>{error}</p>}
      {testResult && <p role="status" style={{ fontSize: 12, color: testResult.ok ? "var(--success)" : "var(--error)" }}>{testResult.message}</p>}
      {saveError && (
        <ErrorPanel
          title={saveError.message}
          detail={saveError.detail}
          onRetry={() => void save(new Event("submit") as unknown as React.FormEvent)}
        />
      )}
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <Button type="button" onClick={onClose} disabled={busy}>Cancelar</Button>
        <Button type="button" onClick={() => void testConnection()} loading={testBusy} disabled={busy}>Testar conexão</Button>
        <Button type="submit" variant="primary" loading={busy}>Salvar conexão</Button>
      </div>
    </form>
  </Modal>;
}
