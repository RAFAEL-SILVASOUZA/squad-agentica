"use client";

import * as React from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  AlertTriangle,
  RefreshCw,
  GitBranch,
  Play,
  CheckCircle2,
  Loader2,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Agent, Pipeline, PipelineNode, PipelineEdge } from "@/lib/types";
import { FlowEditor, type FlowEditorHandle } from "@/components/FlowEditor";
import { PropertiesPanel } from "@/components/flow/properties-panel";
import { StepsList } from "@/components/flow/steps-list";
import {
  validateGraph,
  errorIdSets,
  normalizeServerValidation,
  buildValidationPayload,
  type ValidationError,
} from "@/components/flow/validation";
import { Button } from "@/components/ui/button";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { useToast } from "@/components/ui/toast";
import { ErrorPanel } from "@/components/ui/error-panel";
import { ValidationList } from "@/components/flow/validation-list";
import { RunInputsModal } from "@/components/flow/run-inputs-modal";
import { PipelineHeader } from "@/components/pipelines/pipeline-header";

/**
 * Pipeline detail page: FlowEditor + EdgePanel (fe-flow-edges) + validacao + executar.
 *
 * Endpoints:
 * - GET /api/pipelines/{id} — carrega o grafo
 * - PUT /api/pipelines/{id} — salva o grafo (409 se houver run em andamento)
 * - POST /api/pipelines/validate — validacao de grafo no backend (200 { valid, errors })
 * - POST /api/pipelines/{id}/execute — cria o run (409 pipeline_already_running)
 * - GET /api/agents — agentes disponiveis para a paleta
 *
 * Validacao: o grafo de trabalho e validado localmente (mesmas regras do
 * compiler) e tambem via `POST /api/pipelines/validate` (debounce). Erros
 * sao destacados no canvas (nos/arestas em vermelho) e no painel da aresta;
 * enquanto houver erro, o botao Executar fica bloqueado.
 */

type ValidationState =
  | { status: "idle" }
  | { status: "checking" }
  | { status: "done"; errors: ValidationError[] };

/** Hook: true quando a viewport é < 768px (modo lista do editor, spec 3.6). */
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

export default function PipelineDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { addToast } = useToast();

  const pipelineId = params.id;
  // ?new=1: o pipeline acabou de ser criado (CTA da lista) — o nome já entra em edição.
  const autoEditName = searchParams.get("new") === "1";

  // E13: ref para sincronizar EdgePanel -> canvas interno do FlowEditor
  const flowEditorRef = React.useRef<FlowEditorHandle>(null);

  const [pipeline, setPipeline] = React.useState<Pipeline | null>(null);
  const [agents, setAgents] = React.useState<Agent[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [notFound, setNotFound] = React.useState(false);

  // Grafo de trabalho (espelho do estado local do editor; sincronizado via onGraphChange)
  const [workNodes, setWorkNodes] = React.useState<PipelineNode[]>([]);
  const [workEdges, setWorkEdges] = React.useState<PipelineEdge[]>([]);

  // Selecao atual para o painel de propriedades (spec 3.6)
  const [selection, setSelection] = React.useState<
    { nodeId?: string; edgeId?: string } | null
  >(null);

  // Modo lista no celular (abaixo de 768px, spec 3.6)
  const isMobile = useIsMobile();
  const [mobileSaving, setMobileSaving] = React.useState(false);

  // Validacao
  const [validation, setValidation] = React.useState<ValidationState>({ status: "idle" });
  const [executing, setExecuting] = React.useState(false);

  const fetchPipeline = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [pipelineRes, agentsRes] = await Promise.all([
        api.get<Pipeline>(`/api/pipelines/${pipelineId}`),
        api.list<Agent>("/api/agents", { limit: 100 }),
      ]);
      setPipeline(pipelineRes);
      setWorkNodes(pipelineRes.nodes);
      setWorkEdges(pipelineRes.edges);
      setAgents(agentsRes.items);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 404) {
          setNotFound(true);
        } else {
          setError(err.message);
        }
      } else {
        setError("Falha ao carregar o pipeline");
      }
    } finally {
      setLoading(false);
    }
  }, [pipelineId]);

  React.useEffect(() => {
    fetchPipeline();
  }, [fetchPipeline]);

  // Salvar (PUT /api/pipelines/{id}); usado pelo editor e antes de executar
  const handleSave = React.useCallback(
    async (nodes: PipelineNode[], edges: PipelineEdge[]) => {
      if (!pipeline) return;

      const updated: Pipeline = {
        ...pipeline,
        nodes,
        edges,
        entryNodeId: pipeline.entryNodeId || (nodes.length > 0 ? nodes[0].id : ""),
      };

      try {
        const res = await api.put<Pipeline>(`/api/pipelines/${pipelineId}`, updated);
        setPipeline(res);
        setWorkNodes(res.nodes);
        setWorkEdges(res.edges);
      } catch (err) {
        if (err instanceof ApiError) {
          if (err.status === 409) {
            addToast("error", "O pipeline tem uma execução em andamento. Pare a execução antes de editar.");
          } else {
            throw err;
          }
        } else {
          throw err;
        }
      }
    },
    [pipeline, pipelineId, addToast]
  );

  // PipelineHeader: salva só o campo alterado (nome/descrição/repositório) via PUT.
  const handleHeaderChange = React.useCallback(
    async (patch: Partial<Pipeline>) => {
      if (!pipeline) return;
      try {
        const res = await api.put<Pipeline>(`/api/pipelines/${pipelineId}`, patch);
        setPipeline(res);
      } catch (err) {
        if (err instanceof ApiError) {
          if (err.status === 409) {
            addToast("error", "O pipeline tem uma execução em andamento. Pare a execução antes de editar.");
          } else {
            addToast("error", err.message);
          }
        } else {
          addToast("error", "Não foi possível salvar a alteração.");
        }
      }
    },
    [pipeline, pipelineId, addToast]
  );

  const handlePipelineDeleted = React.useCallback(() => {
    addToast("success", "Pipeline excluído.");
    router.push("/pipelines");
  }, [addToast, router]);

  const handlePipelineDuplicated = React.useCallback(
    (id: string) => {
      router.push(`/pipelines/${id}`);
    },
    [router]
  );

  // O editor notificou que o grafo de trabalho mudou: espelha e revalida
  const handleGraphChange = React.useCallback(
    (nodes: PipelineNode[], edges: PipelineEdge[]) => {
      setWorkNodes(nodes);
      setWorkEdges(edges);
    },
    []
  );

  // ── Painel de propriedades (spec 3.6) ────────────────────────────────
  // Cria/atualiza uma aresta vinda do painel (ex.: entrada de nó -> data edge).
  // Em desktop, empurra para o canvas via setGraph (o onGraphChange devolve o
  // grafo e sincroniza workNodes/workEdges). Em mobile, atualiza direto.
  const handlePanelEdgeChange = React.useCallback((edge: PipelineEdge) => {
    const nextEdges = workEdges.some((e) => e.id === edge.id)
      ? workEdges.map((e) => (e.id === edge.id ? edge : e))
      : [...workEdges, edge];
    if (isMobile) {
      setWorkEdges(nextEdges);
    } else {
      flowEditorRef.current?.setGraph(workNodes, nextEdges);
    }
  }, [isMobile, workNodes, workEdges]);

  // Excluir nó pelo painel.
  const handleDeleteNode = React.useCallback((nodeId: string) => {
    const newNodes = workNodes.filter((n) => n.id !== nodeId);
    const newEdges = workEdges.filter((e) => e.source !== nodeId && e.target !== nodeId);
    setWorkNodes(newNodes);
    setWorkEdges(newEdges);
    setSelection(null);
    if (!isMobile) flowEditorRef.current?.setGraph(newNodes, newEdges);
  }, [isMobile, workNodes, workEdges]);

  // Excluir aresta pelo painel.
  const handleDeleteEdge = React.useCallback((edgeId: string) => {
    const newEdges = workEdges.filter((e) => e.id !== edgeId);
    setWorkEdges(newEdges);
    setSelection(null);
    if (!isMobile) flowEditorRef.current?.setGraph(workNodes, newEdges);
  }, [isMobile, workNodes, workEdges]);

  // Mudança de grafo vinda do modo lista (StepsList, mobile).
  const handleStepsChange = React.useCallback(
    (nodes: PipelineNode[], edges: PipelineEdge[]) => {
      setWorkNodes(nodes);
      setWorkEdges(edges);
    },
    []
  );

  // Validacao: local (imediata, mesmas regras do compiler) + servidor (debounce)
  const entryNodeId =
    pipeline?.entryNodeId || (workNodes.length > 0 ? workNodes[0].id : "");

  const localErrors = React.useMemo(
    () => validateGraph(workNodes, workEdges, entryNodeId),
    [workNodes, workEdges, entryNodeId]
  );

  const validateSeq = React.useRef(0);

  React.useEffect(() => {
    // Sem grafo desenhado ainda: nada para validar
    if (loading || notFound || error || workNodes.length === 0) {
      setValidation({ status: "idle" });
      return;
    }
    setValidation({ status: "checking" });

    const seq = ++validateSeq.current;
    const t = setTimeout(async () => {
      try {
        if (!pipeline) return;
        const res = await api.post<unknown>(
          "/api/pipelines/validate",
          buildValidationPayload(pipeline, workNodes, workEdges)
        );
        if (seq !== validateSeq.current) return;
        const normalized = normalizeServerValidation(res);
        // Merge: erros locais (deterministicos) + erros do servidor nao duplicados
        const localKeys = new Set(
          localErrors.map((e) => `${e.rule}:${e.nodeId ?? ""}:${e.edgeId ?? ""}`)
        );
        const merged = [...localErrors];
        for (const se of normalized.errors) {
          const key = `${se.rule}:${se.nodeId ?? ""}:${se.edgeId ?? ""}`;
          if (!localKeys.has(key)) merged.push(se);
        }
        setValidation({ status: "done", errors: merged });
      } catch (err) {
        if (seq !== validateSeq.current) return;
        // Endpoint de validacao ainda nao existe no backend (fase 6):
        // cai para a validacao local. 4xx de validacao real entra como 200 { valid:false }.
        if (err instanceof ApiError && (err.status === 400 || err.status === 422)) {
          const merged = [...localErrors, { rule: 0, message: err.message }];
          setValidation({ status: "done", errors: merged });
        } else {
          setValidation({ status: "done", errors: localErrors });
        }
      }
    }, 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [localErrors, loading, notFound, error, workNodes.length]);

  // Referencia estavel para os erros ativos (evita re-criacao a cada render)
  const EMPTY_ERRORS = React.useMemo<ValidationError[]>(() => [], []);
  const rawValidation = validation;
  const errors = React.useMemo<ValidationError[]>(
    () => (rawValidation.status === "done" ? rawValidation.errors : EMPTY_ERRORS),
    [rawValidation, EMPTY_ERRORS]
  );
  const hasErrors = errors.length > 0;
  const ids = React.useMemo(() => errorIdSets(errors), [errors]);

  // Executar: POST /api/pipelines/{id}/execute -> cria o run e navega para o monitor
  // Nó de entrada efetivo (o UUID nulo de pipeline recém-criada = 1º nó).
  const entryNode = React.useMemo(
    () => workNodes.find((n) => n.id === entryNodeId) ?? workNodes[0],
    [workNodes, entryNodeId]
  );
  const [runInputsOpen, setRunInputsOpen] = React.useState(false);
  const [errorsOpen, setErrorsOpen] = React.useState(false);
  // Falha ao executar: bloqueia a ação principal, então fica inline com retry.
  const [executeError, setExecuteError] = React.useState<{ message: string; detail?: string } | null>(null);
  const runInputsRef = React.useRef<Record<string, string>>({});


  const handleExecute = React.useCallback(async (runInputs: Record<string, string>) => {
    if (hasErrors || executing || !pipeline) return;
    setExecuting(true);
    setExecuteError(null);
    runInputsRef.current = runInputs;
    try {
      // Salva o grafo antes de executar (estado local pode estar a frente)
      if (workNodes.length > 0) {
        try {
          const updated = buildValidationPayload(pipeline, workNodes, workEdges);
          const res = await api.put<Pipeline>(`/api/pipelines/${pipelineId}`, updated);
          setPipeline(res);
        } catch (err) {
          if (err instanceof ApiError && err.status === 409) {
            addToast("error", "O pipeline tem uma execução em andamento. Pare a execução antes de executar de novo.");
            return;
          }
          throw err;
        }
      }
      await api.post(`/api/pipelines/${pipelineId}/execute`, { inputs: runInputs });
      setRunInputsOpen(false);
      router.push(`/pipelines/${pipelineId}/run?tab=resultado`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Estado, não falha: a pipeline já está em execução, dá pra ver no monitor.
        addToast("error", "Este pipeline já está em execução.");
        return;
      }
      setExecuteError({
        message: "Não foi possível executar a pipeline",
        detail: err instanceof ApiError ? err.describe() : undefined,
      });
    } finally {
      setExecuting(false);
    }
  }, [hasErrors, executing, pipeline, workNodes, workEdges, pipelineId, router, addToast]);

  // Retry do ErrorPanel: reexecuta a mesma ação com os mesmos inputs.
  const handleExecuteRetry = React.useCallback(() => {
    void handleExecute(runInputsRef.current);
  }, [handleExecute]);

  const handleExecuteClick = () => {
    if (hasErrors || executing || !pipeline) return;
    if (entryNode && entryNode.agentSnapshot.inputs.length > 0) setRunInputsOpen(true);
    else void handleExecute({});
  };

  // Loading state
  if (loading) {
    return (
      <div>
        <div style={{ marginBottom: 16 }}>
          <Skeleton height={32} width={200} />
        </div>
        <Skeleton height="calc(100vh - 200px)" />
      </div>
    );
  }

  // Not found
  if (notFound) {
    return (
      <EmptyState
        icon={GitBranch}
        title="Pipeline não encontrado"
        description="Este pipeline não existe ou foi excluído."
        action={
          <Button onClick={() => router.push("/pipelines")}>
            <ArrowLeft size={14} aria-hidden="true" />
            Voltar para pipelines
          </Button>
        }
      />
    );
  }

  // Error state
  if (error) {
    return (
      <div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            padding: "16px 20px",
            background: "var(--bg-elevated)",
            border: "1px solid var(--error)",
            borderRadius: "var(--radius)",
            marginBottom: 16,
          }}
        >
          <AlertTriangle size={18} style={{ color: "var(--error)" }} aria-hidden="true" />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>
              Falha ao carregar o pipeline
            </div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>{error}</div>
          </div>
          <Button
            size="sm"
            onClick={fetchPipeline}
            aria-label="Carregar o pipeline de novo"
          >
            <RefreshCw size={12} aria-hidden="true" />
            Tentar novamente
          </Button>
        </div>
        <Button
          size="sm"
          onClick={() => router.push("/pipelines")}
        >
          <ArrowLeft size={12} aria-hidden="true" />
          Voltar para pipelines
        </Button>
      </div>
    );
  }

  if (!pipeline) return null;

  const isRunning = pipeline.status === "running";

  return (
    <div>
      {/* Breadcrumb */}
      <Breadcrumb items={[{ label: "Pipelines", href: "/pipelines" }, { label: pipeline.name }]} />

      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 16,
        }}
      >
        <div style={{ display: "flex", alignItems: "flex-start", gap: 12, flex: 1, minWidth: 0 }}>
          <Button
            size="sm"
            onClick={() => router.push("/pipelines")}
            aria-label="Voltar para pipelines"
          >
            <ArrowLeft size={14} aria-hidden="true" />
          </Button>
          <div style={{ flex: 1, minWidth: 0 }}>
            <PipelineHeader
              pipeline={pipeline}
              onChange={handleHeaderChange}
              onDeleted={handlePipelineDeleted}
              onDuplicated={handlePipelineDuplicated}
              autoEditName={autoEditName}
            />
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {validation.status === "checking" && (
            <span
              aria-live="polite"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                fontSize: 12,
                color: "var(--text-muted)",
              }}
            >
              <Loader2 size={12} aria-hidden="true" style={{ animation: "spin 1s linear infinite" }} />
              Validando o grafo
            </span>
          )}
          {validation.status === "done" && hasErrors && (
            <div style={{ position: "relative" }}>
              <button
                type="button"
                aria-expanded={errorsOpen}
                aria-haspopup="true"
                onClick={() => setErrorsOpen((o) => !o)}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  fontSize: 12,
                  fontWeight: 600,
                  color: "var(--error)",
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  padding: 0,
                }}
              >
                <AlertTriangle size={13} aria-hidden="true" />
                {errors.length} {errors.length === 1 ? "erro de validação" : "erros de validação"}
              </button>
              {errorsOpen && (
                <div
                  style={{
                    position: "absolute",
                    top: "calc(100% + 6px)",
                    right: 0,
                    zIndex: 20,
                    width: 340,
                    maxHeight: 320,
                    overflowY: "auto",
                    padding: 6,
                    background: "var(--bg-elevated)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius)",
                    boxShadow: "var(--shadow-md, 0 4px 16px rgba(0,0,0,0.2))",
                  }}
                >
                  <ValidationList
                    errors={errors}
                    onSelect={(target) => {
                      flowEditorRef.current?.focusTarget(target);
                      setErrorsOpen(false);
                    }}
                  />
                </div>
              )}
            </div>
          )}
          {validation.status === "done" && !hasErrors && workNodes.length > 0 && (
            <span
              role="status"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                fontSize: 12,
                fontWeight: 600,
                color: "var(--success)",
              }}
            >
              <CheckCircle2 size={13} aria-hidden="true" />
              Grafo válido
            </span>
          )}
          <Button
            size="sm"
            onClick={() => router.push(`/pipelines/${pipelineId}/run`)}
            aria-label="Ver monitor do pipeline"
          >
            Monitor
          </Button>
          <Button
            size="sm"
            variant="primary"
            onClick={handleExecuteClick}
            disabled={hasErrors || isRunning || executing}
            loading={executing}
            aria-label="Executar pipeline"
            title={
              hasErrors
                ? "Corrija os erros de validação antes de executar"
                : isRunning
                  ? "O pipeline já está em execução"
                  : "Cria uma execução e abre o monitor"
            }
          >
            <Play size={13} aria-hidden="true" />
            Executar
          </Button>
        </div>
      </div>

      {/* Erro da execução: inline com "Tentar de novo" (reexecuta o pipeline) */}
      {executeError && (
        <div style={{ marginBottom: 12 }}>
          <ErrorPanel
            title={executeError.message}
            detail={executeError.detail}
            onRetry={() => void handleExecuteRetry()}
          />
        </div>
      )}

      {/* Editor: modo lista no celular (spec 3.6) ou canvas + painel de propriedades */}
      {isMobile ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <StepsList
            pipeline={{ ...pipeline, nodes: workNodes, edges: workEdges }}
            agents={agents}
            onChange={handleStepsChange}
            disabled={pipeline.status === "running"}
            onSelectNode={(nodeId) => setSelection({ nodeId })}
          />
          {selection?.nodeId && (
            <PropertiesPanel
              pipeline={{ ...pipeline, nodes: workNodes, edges: workEdges }}
              selection={selection}
              onChangeNode={(node) => {
                const nextNodes = workNodes.map((n) => (n.id === node.id ? node : n));
                setWorkNodes(nextNodes);
              }}
              onChangeEdge={handlePanelEdgeChange}
              onDeleteNode={handleDeleteNode}
              onDeleteEdge={handleDeleteEdge}
              onClose={() => setSelection(null)}
              onSelectNode={(nodeId) => setSelection({ nodeId })}
              errors={errors}
              disabled={pipeline.status === "running"}
            />
          )}
          <Button
            variant="primary"
            onClick={() => {
              setMobileSaving(true);
              handleSave(workNodes, workEdges)
                .catch(() => addToast("error", "Não foi possível salvar o pipeline."))
                .finally(() => setMobileSaving(false));
            }}
            disabled={isRunning || mobileSaving || workNodes.length === 0}
            loading={mobileSaving}
            aria-label="Salvar pipeline"
          >
            Salvar
          </Button>
        </div>
      ) : (
        <div
          style={{
            display: "flex",
            gap: 12,
            alignItems: "flex-start",
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <FlowEditor
              ref={flowEditorRef}
              pipeline={pipeline}
              agents={agents}
              onSave={handleSave}
              onGraphChange={handleGraphChange}
              onSelectionChange={setSelection}
              errorIdSets={ids}
              disabled={pipeline.status === "running"}
            />
          </div>
          <div style={{ width: 300, flexShrink: 0, position: "sticky", top: 12 }}>
            <PropertiesPanel
              pipeline={{ ...pipeline, nodes: workNodes, edges: workEdges }}
              selection={selection}
              onChangeNode={(node) => {
                const nextNodes = workNodes.map((n) => (n.id === node.id ? node : n));
                flowEditorRef.current?.setGraph(nextNodes, workEdges);
              }}
              onChangeEdge={handlePanelEdgeChange}
              onDeleteNode={handleDeleteNode}
              onDeleteEdge={handleDeleteEdge}
              onClose={() => setSelection(null)}
              onSelectNode={(nodeId) => {
                setSelection({ nodeId });
                flowEditorRef.current?.focusTarget({ nodeId });
              }}
              errors={errors}
              disabled={pipeline.status === "running"}
            />
          </div>
        </div>
      )}
      {entryNode && (
        <RunInputsModal
          open={runInputsOpen}
          agentName={entryNode.agentSnapshot.name}
          inputs={entryNode.agentSnapshot.inputs}
          repository={pipeline.repository ?? null}
          busy={executing}
          onCancel={() => setRunInputsOpen(false)}
          onSubmit={(values) => void handleExecute(values)}
        />
      )}
    </div>
  );
}
