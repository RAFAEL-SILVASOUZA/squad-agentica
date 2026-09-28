"use client";

import * as React from "react";
import { Play } from "lucide-react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { PortDef } from "@/lib/types";

/**
 * Pede os valores das entradas do agente de entrada antes de executar.
 * Sem isto o primeiro agente rodava sem nenhum dado ("Execute your task.").
 * Corpo enviado: POST /api/pipelines/:id/execute { inputs: { nome: valor } }.
 */
export interface RunInputsModalProps {
  open: boolean;
  agentName: string;
  inputs: PortDef[];
  busy?: boolean;
  onCancel: () => void;
  onSubmit: (values: Record<string, string>) => void;
}

export function RunInputsModal({
  open,
  agentName,
  inputs,
  busy = false,
  onCancel,
  onSubmit,
}: RunInputsModalProps) {
  const [values, setValues] = React.useState<Record<string, string>>({});
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (open) {
      setValues({});
      setError(null);
    }
  }, [open]);

  const submit = () => {
    const missing = inputs.filter((p) => p.required && !(values[p.name] ?? "").trim());
    if (missing.length > 0) {
      setError(`Preencha: ${missing.map((p) => p.name).join(", ")}.`);
      return;
    }
    const filled: Record<string, string> = {};
    for (const p of inputs) {
      const v = (values[p.name] ?? "").trim();
      if (v) filled[p.name] = v;
    }
    onSubmit(filled);
  };

  return (
    <Modal
      open={open}
      onClose={onCancel}
      title="Executar pipeline"
      footer={
        <>
          <Button onClick={onCancel} disabled={busy}>
            Cancelar
          </Button>
          <Button variant="primary" onClick={submit} loading={busy}>
            <Play size={13} aria-hidden="true" />
            Executar
          </Button>
        </>
      }
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        <p style={{ margin: 0, fontSize: "13px", color: "var(--text-secondary)" }}>
          Entradas de <strong>{agentName}</strong>, o primeiro agente do pipeline.
        </p>
        {inputs.map((port) => (
          <Textarea
            key={port.name}
            id={`run-input-${port.name}`}
            label={`${port.name}${port.required ? " *" : ""}`}
            hint={`Tipo: ${port.type}`}
            rows={4}
            value={values[port.name] ?? ""}
            onChange={(e) => setValues((v) => ({ ...v, [port.name]: e.target.value }))}
            disabled={busy}
          />
        ))}
        {error && (
          <p role="alert" style={{ margin: 0, fontSize: "12px", color: "var(--error)" }}>
            {error}
          </p>
        )}
      </div>
    </Modal>
  );
}
