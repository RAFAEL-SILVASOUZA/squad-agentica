"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { PipelineMonitor } from "@/components/monitor";

/**
 * Monitor de execução em tempo real (fe-monitor).
 *
 * - Grafo da pipeline em modo leitura com status por nó.
 * - Logs em streaming com auto-scroll pausável, filtro por nó e nível.
 * - Painel do nó selecionado: inputs, outputs, iterações, erro.
 * - Ações: iniciar, pausar, retomar, parar (estados otimistas + reconciliação).
 * - Histórico de runs e checkpoints com retomar a partir do último checkpoint.
 * - Reconexão do WebSocket sem perder eventos (refetch do estado ao reconectar).
 */
export default function PipelineRunPage() {
  const params = useParams<{ id: string }>();
  const pipelineId = params.id;

  return <PipelineMonitor pipelineId={pipelineId} />;
}
