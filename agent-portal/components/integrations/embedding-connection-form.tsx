"use client";

import * as React from "react";
import { api, ApiError } from "@/lib/api";
import type { Integration, LlmProviderKind, EmbeddingConnectionTestResult } from "@/lib/types";
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

/** Lê um valor do config de uma integração como string. */
function strOf(config: Record<string, unknown> | undefined, key: string): string {
  const v = config?.[key];
  return typeof v === "string" ? v : "";
}

/**
 * Formulário de criação/edição de conexão de embedding (adendo 9).
 *
 * Cadastro separado da conexão LLM: o embedding tem a própria base_url,
 * api_key e modelo (ex.: servidor de embeddings em outra porta que o de chat).
 * Config flat: {provider_kind, base_url, api_key, model, dim, query_prefix,
 * document_prefix}. A chave é enviada em claro no create/update; a API a sela
 * (Fernet) e devolve só o hint. Ao editar, deixar a chave vazia mantém a atual.
 * "Testar conexão" chama POST /api/integrations/embedding/test (não persiste).
 */
export function EmbeddingConnectionForm({ connection, onClose, onSaved }: {
  connection?: Integration;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = React.useState(connection?.name ?? "");
  const [providerKind, setProviderKind] = React.useState<LlmProviderKind>(
    (connection?.config.provider_kind as LlmProviderKind) ?? "openai_compatible"
  );
  const [baseUrl, setBaseUrl] = React.useState(strOf(connection?.config, "base_url"));
  const [apiKey, setApiKey] = React.useState("");
  const [model, setModel] = React.useState(strOf(connection?.config, "model"));
  const [dim, setDim] = React.useState(strOf(connection?.config, "dim"));
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [testBusy, setTestBusy] = React.useState(false);
  const [testResult, setTestResult] = React.useState<{ ok: boolean; message: string } | null>(null);
  const [saveError, setSaveError] = React.useState<{ message: string; detail?: string } | null>(null);

  const isMock = providerKind === "mock";

  /** Monta o config de teste (não persiste). */
  function buildTestConfig() {
    const config: Record<string, unknown> = {
      provider_kind: providerKind,
      base_url: baseUrl.trim(),
      model: model.trim(),
    };
    if (dim.trim()) config.dim = Number(dim.trim());
    if (!isMock && apiKey.trim()) config.api_key = apiKey.trim();
    return config;
  }

  async function testConnection() {
    if (testBusy) return;
    if (!model.trim()) {
      setError("Informe o modelo de embedding para testar.");
      return;
    }
    if (!isMock && !apiKey.trim()) {
      setError("Digite a chave de API para testar.");
      return;
    }
    setTestBusy(true);
    setTestResult(null);
    setError("");
    try {
      const result = await api.post<EmbeddingConnectionTestResult>("/api/integrations/embedding/test", {
        type: "embedding",
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
    if (!model.trim()) {
      setError("Informe o modelo de embedding.");
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
      model: model.trim(),
    };
    if (dim.trim()) config.dim = Number(dim.trim());
    if (!isMock) config.api_key = apiKey.trim() || (connection ? "***" : "");

    try {
      if (connection) await api.put(`/api/integrations/${connection.id}`, { name: name.trim(), config });
      else await api.post("/api/integrations", { type: "embedding", name: name.trim(), config });
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

  return <Modal open onClose={() => { if (!busy) onClose(); }} title={connection ? "Editar conexão de embedding" : "Nova conexão de embedding"} size="lg">
    <form onSubmit={(event) => void save(event)} style={{ display: "grid", gap: 16 }}>
      <Input label="Nome" value={name} onChange={(e) => setName(e.target.value)} required maxLength={200} disabled={busy} placeholder="Ex.: Nomic embeddings" />
      <Select label="Provedor" value={providerKind} onValueChange={(v) => setProviderKind(v as LlmProviderKind)} options={PROVIDER_KINDS} disabled={busy} />
      <Input label="Base URL" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} disabled={busy || isMock} placeholder="Ex.: http://192.168.18.4:4321/v1" hint={isMock ? "O mock não usa base URL." : "Obrigatório para servidores compatíveis."} />
      <Input label="Chave de API" type="password" autoComplete="new-password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} required={!connection && !isMock} disabled={busy || isMock}
        hint={isMock ? "O mock não usa chave." : `${connection ? "Deixe vazio para manter a chave atual." : ""} A chave fica criptografada e nunca é mostrada de novo.`} />
      <Input label="Modelo" value={model} onChange={(e) => setModel(e.target.value)} required disabled={busy} placeholder="Ex.: nomic-embed-text-v1.5" hint="Modelo de embedding usado para as bases de conhecimento." />
      <Input label="Dimensão" type="number" value={dim} onChange={(e) => setDim(e.target.value)} disabled={busy} placeholder="Ex.: 768" hint="Opcional. Se vazio, usa a dimensão padrão (1536). O vetor é completado com zeros até a dimensão da coluna." />
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
