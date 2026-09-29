"use client";

import * as React from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import type { GitProvider, Integration, PipelineRepository } from "@/lib/types";
import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/**
 * RepositoryPicker (Task 10).
 * Seleciona conexão Git -> repositório (com busca, spec §4) -> branch,
 * pré-selecionando a branch padrão do repositório.
 *
 * Importante (review round 1, item crítico 1): só notifica o pai (`onChange`)
 * quando há uma escolha *completa* (repositório selecionado, ou branch
 * trocada com repositório já selecionado) ou na limpeza explícita via "Sem
 * repositório". Trocar de conexão é um estado intermediário e NÃO deve
 * disparar `onChange(null)` — isso apagaria um repositório já salvo assim que
 * o usuário começasse a trocar de conexão, antes de concluir a escolha.
 *
 * Endpoints: GET /api/integrations, GET /api/integrations/{id}/repositories,
 * GET /api/integrations/{id}/branches?repo=<fullName>.
 */

const GIT_TYPES: GitProvider[] = ["github", "azure"];

interface RepositoryInfo {
  fullName: string;
  defaultBranch: string;
}

export interface RepositoryPickerProps {
  value: PipelineRepository | null;
  onChange: (value: PipelineRepository | null) => void;
}

export function RepositoryPicker({ value, onChange }: RepositoryPickerProps) {
  const [integrations, setIntegrations] = React.useState<Integration[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");

  const [integrationId, setIntegrationId] = React.useState(value?.integrationId ?? "");
  const [repositories, setRepositories] = React.useState<RepositoryInfo[]>([]);
  const [reposLoading, setReposLoading] = React.useState(false);
  const [reposError, setReposError] = React.useState("");

  const [fullName, setFullName] = React.useState(value?.fullName ?? "");
  const [branches, setBranches] = React.useState<string[]>([]);
  const [baseBranch, setBaseBranch] = React.useState(value?.baseBranch ?? "");
  const [search, setSearch] = React.useState("");

  React.useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      setError("");
      try {
        const items: Integration[] = [];
        let page = 1;
        while (true) {
          const res = await api.list<Integration>("/api/integrations", { page, limit: 100 });
          items.push(...res.items);
          if (!res.items.length || items.length >= res.total) break;
          page++;
        }
        if (active) setIntegrations(items.filter((item) => GIT_TYPES.includes(item.type as GitProvider)));
      } catch (e) {
        if (active) setError(e instanceof ApiError ? e.message : "Não foi possível carregar as conexões Git.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const loadRepositories = React.useCallback(async (id: string) => {
    setReposLoading(true);
    setReposError("");
    try {
      const res = await api.get<{ items: RepositoryInfo[] }>(`/api/integrations/${id}/repositories`);
      setRepositories(res.items);
    } catch (e) {
      setReposError(e instanceof ApiError ? e.message : "Não foi possível carregar os repositórios.");
    } finally {
      setReposLoading(false);
    }
  }, []);

  // Carrega os repositórios da conexão pré-selecionada (edição de um valor existente).
  React.useEffect(() => {
    if (integrationId) void loadRepositories(integrationId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadBranches = React.useCallback(async (id: string, repo: string) => {
    try {
      const res = await api.get<{ items: string[] }>(`/api/integrations/${id}/branches`, { query: { repo } });
      setBranches(res.items);
    } catch {
      setBranches([]);
    }
  }, []);

  // Carrega as branches do repositório pré-selecionado.
  React.useEffect(() => {
    if (integrationId && fullName) void loadBranches(integrationId, fullName);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleIntegrationChange(id: string) {
    // Estado intermediário: NÃO notifica o pai (ver nota no topo do arquivo).
    setIntegrationId(id);
    setFullName("");
    setBaseBranch("");
    setRepositories([]);
    setBranches([]);
    setSearch("");
    if (id) void loadRepositories(id);
  }

  function handleRepositoryChange(name: string) {
    if (!integrationId || !name) return;
    setFullName(name);
    const repo = repositories.find((r) => r.fullName === name);
    const branch = repo?.defaultBranch ?? "";
    setBaseBranch(branch);
    setBranches([]);
    // Escolha completa: agora sim notifica o pai.
    onChange({ integrationId, fullName: name, baseBranch: branch });
    void loadBranches(integrationId, name);
  }

  function handleBranchChange(branch: string) {
    setBaseBranch(branch);
    if (integrationId && fullName) onChange({ integrationId, fullName, baseBranch: branch });
  }

  function clear() {
    setIntegrationId("");
    setFullName("");
    setBaseBranch("");
    setRepositories([]);
    setBranches([]);
    onChange(null);
  }

  if (loading) return <p role="status">Carregando conexões Git...</p>;

  if (error) return <p role="alert">{error}</p>;

  if (integrations.length === 0) {
    return (
      <p style={{ margin: 0 }}>
        Nenhuma conexão Git cadastrada. <Link href="/integrations">Cadastrar conexão Git</Link>
      </p>
    );
  }

  // Revisão final I5: a branch padrão do repositório (e a já escolhida)
  // sempre aparecem, mesmo que o provedor não as devolva na listagem
  // (ex.: repositório com mais branches do que as páginas consultadas).
  const defaultBranch = repositories.find((r) => r.fullName === fullName)?.defaultBranch ?? "";
  const branchOptions = Array.from(
    new Set([defaultBranch, baseBranch, ...branches].filter(Boolean))
  ).map((b) => ({ value: b, label: b }));

  // Spec §4: busca na lista de repositórios do provedor (case-insensitive por fullName).
  const filteredRepositories = repositories.filter((r) =>
    r.fullName.toLowerCase().includes(search.trim().toLowerCase())
  );

  return (
    <div style={{ display: "grid", gap: 12, minWidth: 260 }}>
      <Select
        label="Conexão"
        placeholder="Selecione uma conexão"
        value={integrationId}
        options={integrations.map((i) => ({ value: i.id, label: i.name }))}
        onValueChange={handleIntegrationChange}
      />
      {integrationId &&
        (reposLoading ? (
          <p role="status">Carregando repositórios...</p>
        ) : reposError ? (
          <p role="alert">{reposError}</p>
        ) : (
          <>
            <Input
              label="Buscar repositório"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filtrar por nome"
            />
            <Select
              label="Repositório"
              placeholder="Selecione um repositório"
              value={fullName}
              options={filteredRepositories.map((r) => ({ value: r.fullName, label: r.fullName }))}
              onValueChange={handleRepositoryChange}
            />
          </>
        ))}
      {fullName && (
        <Select
          label="Branch"
          value={baseBranch}
          options={branchOptions}
          onValueChange={handleBranchChange}
        />
      )}
      {value && (
        <Button size="sm" onClick={clear}>
          Sem repositório
        </Button>
      )}
    </div>
  );
}
