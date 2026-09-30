"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useToast } from "@/components/ui/toast";
import { api, ApiError } from "@/lib/api";
import type { Pipeline } from "@/lib/types";

/**
 * Cria uma pipeline (POST /api/pipelines) e navega para o editor
 * (/pipelines/<id>?new=1). Reusado pelo menu "+ Novo" da topbar e por qualquer
 * CTA de criação de pipeline.
 *
 * A lógica é exatamente a do `handleCreate` da lista de pipelines
 * (app/(dashboard)/pipelines/page.tsx): payload padrão, navegação com ?new=1
 * (o nome já entra em edição) e toast de erro assertivo.
 */

export interface CreatePipelineOptions {
  name?: string;
  description?: string;
}

export async function createPipeline(opts: CreatePipelineOptions = {}): Promise<Pipeline | null> {
  const res = await api.post<Pipeline>("/api/pipelines", {
    name: opts.name ?? "Novo pipeline",
    description: opts.description ?? "",
    entryNodeId: "",
    nodes: [],
    edges: [],
  });
  return res;
}

/**
 * Cria a pipeline e navega para o editor. Retorna a pipeline criada (ou null
 * em caso de erro). Usado pelo menu "+ Novo" da topbar.
 */
export function useCreatePipelineAndNavigate(): () => Promise<Pipeline | null> {
  const router = useRouter();
  const { addToast } = useToast();

  return React.useCallback(
    () =>
      (async () => {
        try {
          const res = await createPipeline();
          if (!res) return null;
          // ?new=1: o editor já abre com o nome em edição.
          router.push(`/pipelines/${res.id}?new=1`);
          return res;
        } catch (err) {
          if (err instanceof ApiError) {
            addToast("error", err.message);
          } else {
            addToast("error", "Falha ao criar pipeline");
          }
          return null;
        }
      })(),
    [router, addToast]
  );
}
