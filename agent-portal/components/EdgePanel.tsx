"use client";

import * as React from "react";
import { X, Shield, AlertCircle } from "lucide-react";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Toggle } from "@/components/ui/toggle";
import { Button } from "@/components/ui/button";
import type {
  EdgeCondition,
  FlowAction,
  NotificationChannel,
  PipelineEdge,
  PipelineNode,
  PortDef,
} from "@/lib/types";
import { validateDataMapping, flowActions } from "./flow/validation";

/**
 * EdgePanel — configuração de uma aresta selecionada no editor de pipelines.
 *
 * Renderizado pelo fe-flow-edges dentro do slot `edgePanelSlot` do FlowEditor
 * (posicionado top: 56px, right: 12px — design system §2.11).
 *
 * Campos por tipo de aresta (spec 4.2):
 * - flow: tipo, condition (field=action, operator, value), requiresApproval,
 *         approvalChannel, approvalMessage, rejectTarget.
 * - data: tipo, dataMapping (sourceOutput -> targetInput com checagem de tipo).
 *
 * `rejectTarget`: node para onde a aresta "devolve" quando o humano rejeita a
 * aprovacao. Em V1 o compiler usa o `reject_handler` derivado (source ou encerra),
 * entao este campo e apenas informativo (label); nao altera o grafo persistido.
 */

export interface EdgePanelProps {
  /** Edge selecionada (fonte de verdade para os valores iniciais). */
  edge: PipelineEdge;
  /** Todos os nós, para resolver os selects de dataMapping. */
  nodes: PipelineNode[];
  /** Chama quando um campo muda. O painel aplica ao estado e notifica o canvas. */
  onChange: (edge: PipelineEdge) => void;
  /** Fecha o painel (deseleciona a aresta). */
  onClose: () => void;
  /** Mensagens de validacao local/grafo referentes a esta aresta. */
  errors?: string[];
  disabled?: boolean;
}

const OPERATOR_LABELS: Record<EdgeCondition["operator"], string> = {
  eq: "igual a",
  neq: "diferente de",
  in: "em",
  not_in: "fora de",
};

const CHANNELS: NotificationChannel[] = ["in-app", "email", "teams", "slack"];

export function EdgePanel({
  edge,
  nodes,
  onChange,
  onClose,
  errors,
  disabled = false,
}: EdgePanelProps) {
  const sourceNode = nodes.find((n) => n.id === edge.source);
  const targetNode = nodes.find((n) => n.id === edge.target);

  const isData = edge.type === "data";

  const sourceOutputs: PortDef[] = sourceNode?.agentSnapshot.outputs ?? [];
  const targetInputs: PortDef[] = targetNode?.agentSnapshot.inputs ?? [];

  const condition = edge.condition;
  const dataMapping = edge.dataMapping;

  // Operador mantido em estado local: o painel e controlado pelo canvas (o
  // prop `edge` so atualiza apos o canvas confirmar). Sem estado local, trocar
  // o operador nao refletiria nos handlers de acao na mesma sessao de digito.
  const [operator, setOperator] = React.useState<EdgeCondition["operator"]>(
    condition?.operator ?? "eq"
  );
  React.useEffect(() => {
    if (condition) setOperator(condition.operator);
  }, [condition]);

  // dataMapping em estado local: o painel e controlado pelo canvas, e o prop
  // `edge` so atualiza apos confirmacao. Sem estado local, trocar um campo
  // perdria o valor do outro na sequencia de digitacao.
  const [draftMapping, setDraftMapping] = React.useState<{
    sourceOutput: string;
    targetInput: string;
  }>({
    sourceOutput: dataMapping?.sourceOutput ?? "",
    targetInput: dataMapping?.targetInput ?? "",
  });
  // Ref espelho sincrono: entre dois onChange no mesmo tick, setState ainda
  // nao refletiu, mas o ref ja tem o valor atual.
  const draftMappingRef = React.useRef(draftMapping);
  draftMappingRef.current = draftMapping;

  React.useEffect(() => {
    const next = {
      sourceOutput: dataMapping?.sourceOutput ?? "",
      targetInput: dataMapping?.targetInput ?? "",
    };
    setDraftMapping(next);
    draftMappingRef.current = next;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [edge.id]);

  const mappingError = isData
    ? validateDataMapping(draftMapping, sourceNode, targetNode)
    : null;

  const actions = flowActions();

  const setConditionValue = (action: FlowAction) => {
    const current = operator;
    let value: string | string[];
    if (current === "in" || current === "not_in") {
      const arr = Array.isArray(condition?.value)
        ? [...condition.value]
        : condition?.value
          ? [condition.value as string]
          : [];
      value = arr.includes(action) ? arr.filter((a) => a !== action) : [...arr, action];
    } else {
      value = action;
    }
    onChange({
      ...edge,
      condition: { field: "action", operator: current, value },
    });
  };

  const selectedActions = React.useMemo(() => {
    if (!condition) return [] as string[];
    return Array.isArray(condition.value)
      ? condition.value
      : condition.value
        ? [condition.value as string]
        : [];
  }, [condition]);

  const multi = operator === "in" || operator === "not_in";

  const handleMappingChange = (
    which: "sourceOutput" | "targetInput",
    name: string
  ) => {
    const next = {
      ...draftMappingRef.current,
      [which]: name,
    };
    draftMappingRef.current = next;
    setDraftMapping(next);
    onChange({
      ...edge,
      dataMapping: next,
    });
  };

  const handleRequiresApproval = (checked: boolean) => {
    const patch: Partial<PipelineEdge> = { requiresApproval: checked };
    if (checked) {
      if (!edge.approvalChannel) patch.approvalChannel = "in-app";
      if (!edge.approvalMessage) patch.approvalMessage = "";
    }
    onChange({ ...edge, ...patch });
  };

  const allErrors = errors ?? [];

  return (
    <div
      role="region"
      aria-label={`Configuração da aresta ${sourceNode?.agentSnapshot.name ?? edge.source} para ${targetNode?.agentSnapshot.name ?? edge.target}`}
      style={{
        width: 260,
        background: "var(--bg-elevated)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius)",
        boxShadow: "var(--shadow-lg)",
        overflow: "hidden",
        fontSize: 12,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "10px 12px",
          borderBottom: "1px solid var(--border)",
          fontWeight: 600,
        }}
      >
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {sourceNode?.agentSnapshot.name ?? edge.source} →{" "}
          {targetNode?.agentSnapshot.name ?? edge.target}
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Fechar painel da aresta"
          style={{
            border: "none",
            background: "none",
            color: "var(--text-muted)",
            cursor: "pointer",
            padding: 0,
            display: "flex",
          }}
        >
          <X size={14} aria-hidden="true" />
        </button>
      </div>

      <div
        style={{
          padding: "12px",
          display: "flex",
          flexDirection: "column",
          gap: "10px",
          maxHeight: "calc(100vh - 220px)",
          overflowY: "auto",
        }}
      >
        {/* Tipo da aresta */}
        <Select
          label="Tipo"
          id="edge-type"
          value={edge.type}
          disabled={disabled}
          onValueChange={(v) =>
            onChange({
              ...edge,
              type: (v as "flow" | "data"),
              // limpa campos incoerentes ao trocar de tipo
              condition: v === "flow" ? edge.condition : undefined,
              dataMapping: v === "data" ? edge.dataMapping : undefined,
            })
          }
          options={[
            { value: "flow", label: "Fluxo (ordem de execução)" },
            { value: "data", label: "Dados (propaga output)" },
          ]}
        />

        {isData && (
          <p style={{ margin: 0, fontSize: 11, color: "var(--text-muted)" }}>
            Dados: leva a saída escolhida para a entrada do próximo agente e já define a ordem
          </p>
        )}

        {/* FLOW: condicao */}
        {!isData && (
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <div
              style={{
                fontSize: 11,
                fontWeight: 600,
                textTransform: "uppercase",
                letterSpacing: "0.5px",
                color: "var(--text-muted)",
              }}
            >
              Condição
            </div>
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                cursor: disabled ? "not-allowed" : "pointer",
                opacity: disabled ? 0.6 : 1,
              }}
            >
              <input
                id="edge-has-condition"
                type="checkbox"
                aria-label="Definir condição de ação"
                checked={!!condition}
                disabled={disabled}
                onChange={(e) => {
                  if (e.target.checked) {
                    onChange({
                      ...edge,
                      condition: { field: "action", operator: "eq", value: "follow" },
                    });
                  } else {
                    onChange({ ...edge, condition: undefined });
                  }
                }}
                style={{ accentColor: "var(--accent)" }}
              />
              <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                Condição de ação (senão, incondicional)
              </span>
            </label>
            {condition && (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "8px",
                  paddingLeft: 4,
                }}
              >
                <Select
                  label="Operador"
                  id="edge-operator"
                  value={operator}
                  disabled={disabled}
                  onValueChange={(v) => {
                    const nextOp = v as EdgeCondition["operator"];
                    setOperator(nextOp);
                    onChange({
                      ...edge,
                      condition: {
                        field: "action",
                        operator: nextOp,
                        value: condition.value,
                      },
                    });
                  }}
                  options={(
                    ["eq", "neq", "in", "not_in"] as const
                  ).map((op) => ({
                    value: op,
                    label: OPERATOR_LABELS[op],
                  }))}
                />
                {multi ? (
                  <div>
                    <span
                      id="edge-action-label"
                      style={{
                        fontSize: 13,
                        fontWeight: 500,
                        color: "var(--text)",
                        display: "block",
                        marginBottom: 6,
                      }}
                    >
                      Ações
                    </span>
                    <div
                      style={{ display: "flex", flexDirection: "column", gap: 4 }}
                    >
                      {actions.map((a) => (
                        <label
                          key={a}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                            cursor: disabled ? "not-allowed" : "pointer",
                            opacity: disabled ? 0.6 : 1,
                          }}
                        >
                          <input
                            type="checkbox"
                            aria-labelledby="edge-action-label"
                            checked={selectedActions.includes(a)}
                            disabled={disabled}
                            onChange={() => setConditionValue(a)}
                            style={{ accentColor: "var(--accent)" }}
                          />
                          <span>{a}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                ) : (
                  <Select
                    label="Ação"
                    id="edge-action"
                    value={typeof condition.value === "string" ? condition.value : ""}
                    disabled={disabled}
                    onValueChange={(v) =>
                      onChange({
                        ...edge,
                        condition: {
                          field: "action",
                          operator,
                          value: v,
                        },
                      })
                    }
                    options={actions.map((a) => ({ value: a, label: a }))}
                  />
                )}
              </div>
            )}
          </div>
        )}

        {/* DATA: dataMapping */}
        {isData && (
          <div
            style={{ display: "flex", flexDirection: "column", gap: "8px" }}
          >
            <div
              style={{
                fontSize: 11,
                fontWeight: 600,
                textTransform: "uppercase",
                letterSpacing: "0.5px",
                color: "var(--text-muted)",
              }}
            >
              Data Mapping
            </div>
            <Select
              label="Output do source"
              id="edge-source-output"
              value={dataMapping?.sourceOutput ?? ""}
              disabled={disabled}
              placeholder={
                sourceOutputs.length ? "Selecione um output" : "Sem outputs disponíveis"
              }
              onValueChange={(v) => handleMappingChange("sourceOutput", v)}
              options={sourceOutputs.map((p) => ({
                value: p.name,
                label: `${p.name} (${p.type})`,
              }))}
            />
            <Select
              label="Input do target"
              id="edge-target-input"
              value={dataMapping?.targetInput ?? ""}
              disabled={disabled}
              placeholder={
                targetInputs.length ? "Selecione um input" : "Sem inputs disponíveis"
              }
              onValueChange={(v) => handleMappingChange("targetInput", v)}
              options={targetInputs.map((p) => ({
                value: p.name,
                label: `${p.name} (${p.type})`,
              }))}
            />
            {mappingError ? (
              <p
                role="alert"
                style={{
                  display: "flex",
                  gap: 6,
                  alignItems: "flex-start",
                  color: "var(--error)",
                  fontSize: 12,
                  margin: 0,
                }}
              >
                <AlertCircle size={13} aria-hidden="true" style={{ flexShrink: 0, marginTop: 1 }} />
                {mappingError}
              </p>
            ) : (
              draftMapping.sourceOutput &&
              draftMapping.targetInput && (
                <p
                  style={{
                    color: "var(--text-muted)",
                    fontSize: 11,
                    margin: 0,
                  }}
                >
                  Ordem de execução: implícita (roda após o source), a menos que
                  exista uma flow edge explícita entre o mesmo par.
                </p>
              )
            )}
          </div>
        )}

        {/* Label */}
        <div
          style={{ display: "flex", flexDirection: "column", gap: "6px" }}
        >
          <label
            htmlFor="edge-label"
            style={{ fontSize: 13, fontWeight: 500, color: "var(--text)" }}
          >
            Rótulo
          </label>
          <input
            id="edge-label"
            type="text"
            value={edge.label ?? ""}
            disabled={disabled}
            placeholder='ex.: "aprovado", "reprovado", "seguir"'
            onChange={(e) => onChange({ ...edge, label: e.target.value })}
            style={{
              padding: "8px 12px",
              borderRadius: "var(--radius-sm)",
              border: "1px solid var(--border)",
              background: "var(--bg-elevated)",
              color: "var(--text)",
              fontSize: 12,
              outline: "none",
              width: "100%",
            }}
          />
        </div>

        {/* Aprovação */}
        <div
          style={{
            borderTop: "1px solid var(--border-subtle)",
            paddingTop: 4,
            display: "flex",
            flexDirection: "column",
            gap: "8px",
          }}
        >
          <Toggle
            label="Requer aprovação"
            description="Pausa aqui até alguém aprovar"
            checked={edge.requiresApproval}
            disabled={disabled}
            onChange={handleRequiresApproval}
            id="edge-requires-approval"
          />
          {edge.requiresApproval && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "8px",
                paddingLeft: 4,
              }}
            >
              <Select
                label="Canal de notificação"
                id="edge-approval-channel"
                value={edge.approvalChannel ?? "in-app"}
                disabled={disabled}
                onValueChange={(v) =>
                  onChange({ ...edge, approvalChannel: v as NotificationChannel })
                }
                options={CHANNELS.map((c) => ({ value: c, label: c }))}
              />
              <Textarea
                label="Mensagem de notificação"
                id="edge-approval-message"
                rows={2}
                value={edge.approvalMessage ?? ""}
                disabled={disabled}
                placeholder="Contexto enviado ao humano na notificação"
                onChange={(e) =>
                  onChange({ ...edge, approvalMessage: e.target.value })
                }
              />
              <div
                style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--text-muted)" }}
              >
                <Shield size={12} aria-hidden="true" />
                <span>
                  Alvo de rejeição (V1): derivado pelo compiler — devolve ao
                  source ou encerra (reject_handler).
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Erros de grafo */}
        {allErrors.length > 0 && (
          <div
            role="alert"
            style={{
              borderTop: "1px solid var(--border-subtle)",
              paddingTop: 8,
              display: "flex",
              flexDirection: "column",
              gap: 6,
            }}
          >
            {allErrors.map((msg, i) => (
              <p
                key={i}
                style={{
                  display: "flex",
                  gap: 6,
                  alignItems: "flex-start",
                  color: "var(--error)",
                  fontSize: 11,
                  margin: 0,
                }}
              >
                <AlertCircle size={12} aria-hidden="true" style={{ flexShrink: 0, marginTop: 1 }} />
                {msg}
              </p>
            ))}
          </div>
        )}

        <Button size="sm" onClick={onClose} disabled={disabled}>
          Fechar
        </Button>
      </div>
    </div>
  );
}
