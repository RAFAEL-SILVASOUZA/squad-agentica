"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { PipelineMonitor } from "@/components/monitor";

/**
 * Monitor de execução em tempo real (fe-monitor).
 *
 * - Cabeçalho com status do run, repositório e link do PR (ou falha de
 *   publicação com nova tentativa); ações iniciar, pausar, retomar, parar.
 * - Faixa de etapas na ordem do grafo; "Ver grafo" abre o grafo num modal.
 * - Abas (?tab=): Resultado (saída dos agentes em markdown), Arquivos do
 *   projeto, Logs (filtros por agente e nível) e Histórico (checkpoints).
 * - Reconexão do WebSocket sem perder eventos (refetch do estado ao reconectar).
 */
export default function PipelineRunPage() {
  const params = useParams<{ id: string }>();
  const pipelineId = params.id;

  return <PipelineMonitor pipelineId={pipelineId} />;
}
