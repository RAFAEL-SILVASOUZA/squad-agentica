"use client";

import * as React from "react";
import { GitBranch, X } from "lucide-react";
import type { Pipeline } from "@/lib/types";
import { RepositoryPicker } from "./repository-picker";
import { PipelineActionsMenu } from "./pipeline-actions-menu";

/**
 * PipelineHeader (Task 10).
 * Cabeçalho do editor: nome/descrição editáveis inline, chip de repositório
 * (popover com RepositoryPicker) e menu "Mais ações" (Duplicar/Excluir).
 *
 * `onChange` é usado para salvar cada campo (nome/descrição/repositório) via
 * PUT /api/pipelines/{id} feito pela página; exclusão e duplicação são
 * chamadas diretamente aqui (DELETE e POST .../duplicate).
 */
export interface PipelineHeaderProps {
  pipeline: Pipeline;
  onChange: (patch: Partial<Pipeline>) => void;
  onDeleted: () => void;
  onDuplicated: (id: string) => void;
  /** Liga a edição do nome assim que o componente monta (?new=1). */
  autoEditName?: boolean;
}

export function PipelineHeader({
  pipeline,
  onChange,
  onDeleted,
  onDuplicated,
  autoEditName = false,
}: PipelineHeaderProps) {
  const [editingName, setEditingName] = React.useState(autoEditName);
  const [nameValue, setNameValue] = React.useState(pipeline.name);
  const [nameError, setNameError] = React.useState("");

  const [editingDescription, setEditingDescription] = React.useState(false);
  const [descriptionValue, setDescriptionValue] = React.useState(pipeline.description);

  const [repoOpen, setRepoOpen] = React.useState(false);

  const repoRef = React.useRef<HTMLDivElement>(null);

  // Mantém os buffers locais em sincronia com o pipeline vindo de fora,
  // exceto enquanto o usuário está editando aquele campo.
  React.useEffect(() => {
    if (!editingName) setNameValue(pipeline.name);
  }, [pipeline.name, editingName]);
  React.useEffect(() => {
    if (!editingDescription) setDescriptionValue(pipeline.description);
  }, [pipeline.description, editingDescription]);

  function commitName() {
    const trimmed = nameValue.trim();
    if (!trimmed) {
      setNameError("Informe um nome para o pipeline.");
      return;
    }
    setNameError("");
    setEditingName(false);
    if (trimmed !== pipeline.name) onChange({ name: trimmed });
  }

  function cancelNameEdit() {
    setNameValue(pipeline.name);
    setNameError("");
    setEditingName(false);
  }

  function commitDescription() {
    setEditingDescription(false);
    if (descriptionValue !== pipeline.description) onChange({ description: descriptionValue });
  }

  function cancelDescriptionEdit() {
    setDescriptionValue(pipeline.description);
    setEditingDescription(false);
  }

  // Esc/clique fora fecham o popover do repositório.
  React.useEffect(() => {
    if (!repoOpen) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setRepoOpen(false);
    }
    function onClickOutside(e: MouseEvent) {
      if (repoRef.current && !repoRef.current.contains(e.target as Node)) setRepoOpen(false);
    }
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onClickOutside);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onClickOutside);
    };
  }, [repoOpen]);

  const repository = pipeline.repository;
  const repoLabel = repository ? `Repositório: ${repository.fullName} (${repository.baseBranch})` : "Sem repositório";

  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: 240 }}>
          {editingName ? (
            <div>
              <input
                aria-label="Nome do pipeline"
                value={nameValue}
                autoFocus
                onChange={(e) => setNameValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commitName();
                  if (e.key === "Escape") cancelNameEdit();
                }}
                onBlur={commitName}
                style={{
                  fontSize: "var(--text-title)",
                  fontWeight: 700,
                  color: "var(--text)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius-sm)",
                  padding: "4px 8px",
                  width: "100%",
                  fontFamily: "var(--font)",
                  background: "var(--bg-elevated)",
                }}
              />
              {nameError && (
                <p role="alert" style={{ color: "var(--error)", fontSize: 12, margin: "4px 0 0" }}>
                  {nameError}
                </p>
              )}
            </div>
          ) : (
            <h1
              onClick={() => setEditingName(true)}
              style={{ fontSize: "var(--text-title)", fontWeight: 700, color: "var(--text)", margin: 0, cursor: "pointer" }}
              title="Clique para editar o nome"
            >
              {pipeline.name}
            </h1>
          )}

          {editingDescription ? (
            <textarea
              aria-label="Descrição do pipeline"
              value={descriptionValue}
              autoFocus
              rows={1}
              onChange={(e) => setDescriptionValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  commitDescription();
                }
                if (e.key === "Escape") cancelDescriptionEdit();
              }}
              onBlur={commitDescription}
              style={{
                fontSize: "var(--text-lg)",
                color: "var(--text-secondary)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
                padding: "4px 8px",
                width: "100%",
                marginTop: 4,
                resize: "none",
                fontFamily: "var(--font)",
                background: "var(--bg-elevated)",
              }}
            />
          ) : (
            <p
              onClick={() => setEditingDescription(true)}
              style={{
                fontSize: "var(--text-lg)",
                color: "var(--text-secondary)",
                margin: "2px 0 0",
                cursor: "pointer",
                minHeight: 18,
              }}
              title="Clique para editar a descrição"
            >
              {pipeline.description || "Adicionar descrição"}
            </p>
          )}

          <div ref={repoRef} style={{ position: "relative", marginTop: 8, display: "inline-block" }}>
            <button
              type="button"
              onClick={() => setRepoOpen((v) => !v)}
              aria-haspopup="dialog"
              aria-expanded={repoOpen}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                fontSize: 12,
                color: "var(--text-secondary)",
                background: "var(--bg-card)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
                padding: "4px 10px",
                cursor: "pointer",
              }}
            >
              <GitBranch size={12} aria-hidden="true" />
              {repoLabel}
            </button>
            {repoOpen && (
              <div
                role="dialog"
                aria-label="Repositório do pipeline"
                style={{
                  position: "absolute",
                  top: "calc(100% + 6px)",
                  left: 0,
                  zIndex: 20,
                  background: "var(--bg-elevated)",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius)",
                  boxShadow: "var(--shadow-lg)",
                  padding: 14,
                }}
              >
                <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
                  <button
                    type="button"
                    aria-label="Fechar"
                    onClick={() => setRepoOpen(false)}
                    style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)" }}
                  >
                    <X size={14} aria-hidden="true" />
                  </button>
                </div>
                <RepositoryPicker
                  value={repository}
                  onChange={(value) => {
                    onChange({ repository: value });
                    if (!value) setRepoOpen(false);
                  }}
                />
              </div>
            )}
          </div>
        </div>

        <PipelineActionsMenu
          pipelineId={pipeline.id}
          pipelineName={pipeline.name}
          onDuplicated={onDuplicated}
          onDeleted={onDeleted}
        />
      </div>
    </div>
  );
}
