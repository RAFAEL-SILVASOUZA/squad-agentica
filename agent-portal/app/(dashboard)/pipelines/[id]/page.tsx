"use client";

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
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
import { EdgePanel } from "@/components/EdgePanel";
import {
  validateGraph,
  errorIdSets,
  normalizeServerValidation,
  buildValidationPayload,
  type ValidationError,
} from "@/components/flow/validation";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { useToast } from "@/components/ui/toast";
import { RunInputsModal } from "@/components/flow/run-inputs-modal";

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

export default function PipelineDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { addToast } = useToast();

  const pipelineId = params.id;

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

  // Aresta selecionada (EdgePanel)
  const [selectedEdge, setSelectedEdge] = React.useState<PipelineEdge | null>(null);

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

  // O editor notificou que o grafo de trabalho mudou: espelha e revalida
  const handleGraphChange = React.useCallback(
    (nodes: PipelineNode[], edges: PipelineEdge[]) => {
      setWorkNodes(nodes);
      setWorkEdges(edges);
      // Mantem a aresta selecionada em sincronia com o grafo de trabalho
      setSelectedEdge((prev) => {
        if (!prev) return prev;
        return edges.find((e) => e.id === prev.id) ?? prev;
      });
    },
    []
  );

  // Mudanca vinda do EdgePanel: espelha, revalida e sincroniza o canvas
  // E13: sem o updateEdge no FlowEditor, a edição ficava só na pagina e o
  // Save (que usa o estado interno do editor) nunca gravava a mudança.
  const handleEdgeChange = React.useCallback((edge: PipelineEdge) => {
    setSelectedEdge(edge);
    setWorkEdges((prev) => prev.map((e) => (e.id === edge.id ? edge : e)));
    flowEditorRef.current?.updateEdge(edge);
  }, []);

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

  // Erros da aresta selecionada (mensagens para o painel)
  const selectedEdgeErrors = React.useMemo(
    () =>
      selectedEdge
        ? errors.filter((e) => e.edgeId === selectedEdge.id).map((e) => e.message)
        : [],
    [errors, selectedEdge]
  );

  // Executar: POST /api/pipelines/{id}/execute -> cria o run e navega para o monitor
  // Nó de entrada efetivo (o UUID nulo de pipeline recém-criada = 1º nó).
  const entryNode = React.useMemo(
    () => workNodes.find((n) => n.id === entryNodeId) ?? workNodes[0],
    [workNodes, entryNodeId]
  );
  const [runInputsOpen, setRunInputsOpen] = React.useState(false);


  const handleExecute = React.useCallback(async (runInputs: Record<string, string>) => {
    if (hasErrors || executing || !pipeline) return;
    setExecuting(true);
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
      router.push(`/pipelines/${pipelineId}/run`);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          addToast("error", "Este pipeline já está em execução.");
        } else if (err.status === 400) {
          addToast("error", "Grafo inválido. Corrija os erros de validação antes de executar.");
        } else {
          addToast("error", err.message || "Falha ao executar o pipeline");
        }
      } else {
        addToast("error", "Falha ao executar o pipeline");
      }
    } finally {
      setExecuting(false);
    }
  }, [hasErrors, executing, pipeline, workNodes, workEdges, pipelineId, router, addToast]);

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
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 16,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Button
            size="sm"
            onClick={() => router.push("/pipelines")}
            aria-label="Voltar para pipelines"
          >
            <ArrowLeft size={14} aria-hidden="true" />
          </Button>
          <div>
            <h1
              style={{
                fontSize: "var(--text-title)",
                fontWeight: 700,
                color: "var(--text)",
                margin: 0,
              }}
            >
              {pipeline.name}
            </h1>
            {pipeline.description && (
              <p
                style={{
                  fontSize: "var(--text-lg)",
                  color: "var(--text-secondary)",
                  margin: "2px 0 0",
                }}
              >
                {pipeline.description}
              </p>
            )}
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
            <span
              role="status"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                fontSize: 12,
                fontWeight: 600,
                color: "var(--error)",
              }}
            >
              <AlertTriangle size={13} aria-hidden="true" />
              {errors.length} {errors.length === 1 ? "erro de validação" : "erros de validação"}
            </span>
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

      {/* Flow Editor + EdgePanel */}
      <FlowEditor
        ref={flowEditorRef}
        pipeline={pipeline}
        agents={agents}
        onSave={handleSave}
        onEdgeSelect={setSelectedEdge}
        onGraphChange={handleGraphChange}
        errorIdSets={ids}
        disabled={pipeline.status === "running"}
        edgePanelSlot={
          selectedEdge ? (
            <EdgePanel
              key={selectedEdge.id}
              edge={selectedEdge}
              nodes={workNodes}
              onChange={handleEdgeChange}
              onClose={() => setSelectedEdge(null)}
              errors={selectedEdgeErrors}
              disabled={pipeline.status === "running"}
            />
          ) : null
        }
      />
      {entryNode && (
        <RunInputsModal
          open={runInputsOpen}
          agentName={entryNode.agentSnapshot.name}
          inputs={entryNode.agentSnapshot.inputs}
          busy={executing}
          onCancel={() => setRunInputsOpen(false)}
          onSubmit={(values) => void handleExecute(values)}
        />
      )}
    </div>
  );
}
