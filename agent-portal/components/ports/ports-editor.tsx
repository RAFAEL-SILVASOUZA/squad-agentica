"use client";

import * as React from "react";

export type Port = { name: string; type: string; required: boolean; description?: string };

export interface PortsEditorProps {
  label: string;
  value: Port[];
  onChange: (ports: Port[]) => void;
  types: string[];
}

function cleanPort(p: Port): Port {
  const out: Port = { name: p.name, type: p.type, required: p.required };
  if (p.description && p.description.trim() !== "") out.description = p.description;
  return out;
}

const inputStyle: React.CSSProperties = {
  padding: "6px 8px",
  borderRadius: "var(--radius-sm)",
  border: "1px solid var(--border)",
  background: "var(--bg-elevated)",
  color: "var(--text)",
  fontSize: 13,
  minWidth: 0,
};

const btnStyle: React.CSSProperties = {
  padding: "6px 12px",
  borderRadius: "var(--radius-sm)",
  border: "1px solid var(--border)",
  background: "var(--bg-card)",
  color: "var(--text)",
  fontSize: 13,
  cursor: "pointer",
};

/**
 * Editor estruturado de entradas/saídas (ports). Componente controlado:
 * `value`/`onChange`. Cada linha tem nome, tipo (select), obrigatório (toggle)
 * e descrição. "+ Adicionar", remover por linha e "Ver JSON" (somente leitura).
 * Valida nome vazio ("Nome obrigatório") e nome duplicado ("Nome repetido")
 * com erro inline; `onChange` só é chamado com listas válidas.
 */
export function PortsEditor({ label, value, onChange, types }: PortsEditorProps) {
  const [showJson, setShowJson] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const updatePort = (idx: number, patch: Partial<Port>) => {
    const next = value.map((p, i) => (i === idx ? { ...p, ...patch } : p));
    const edited = next[idx];
    if (edited.name.trim() === "") {
      setError("Nome obrigatório");
      return;
    }
    const dup = next.some((p, i) => i !== idx && p.name.trim() === edited.name.trim());
    if (dup) {
      setError("Nome repetido");
      return;
    }
    setError(null);
    onChange(next.map(cleanPort));
  };

  const addPort = () => {
    const next = [...value, { name: "", type: types[0] ?? "", required: false }];
    setError(null);
    onChange(next.map(cleanPort));
  };

  const removePort = (idx: number) => {
    const next = value.filter((_, i) => i !== idx);
    setError(null);
    onChange(next.map(cleanPort));
  };

  return (
    <div style={{ display: "grid", gap: 8 }}>
      <label style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>{label}</label>
      {value.map((port, i) => (
        <div
          key={i}
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 110px auto 1fr auto",
            gap: 8,
            alignItems: "center",
            padding: 8,
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)",
            background: "var(--bg-card)",
          }}
        >
          <input
            value={port.name}
            onChange={(e) => updatePort(i, { name: e.target.value })}
            placeholder="Nome"
            aria-label={`Nome do port ${i + 1}`}
            style={inputStyle}
          />
          <select
            value={port.type}
            onChange={(e) => updatePort(i, { type: e.target.value })}
            aria-label={`Tipo do port ${i + 1}`}
            style={inputStyle}
          >
            {types.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: 4,
              fontSize: 12,
              color: "var(--text-secondary)",
              whiteSpace: "nowrap",
            }}
          >
            <input
              type="checkbox"
              checked={port.required}
              onChange={(e) => updatePort(i, { required: e.target.checked })}
              aria-label={`Obrigatório (port ${i + 1})`}
            />
            Obrig.
          </label>
          <input
            value={port.description ?? ""}
            onChange={(e) => updatePort(i, { description: e.target.value })}
            placeholder="Descrição"
            aria-label={`Descrição do port ${i + 1}`}
            style={inputStyle}
          />
          <button
            type="button"
            onClick={() => removePort(i)}
            aria-label={`Remover port ${i + 1}`}
            style={{
              border: "none",
              background: "transparent",
              color: "var(--text-secondary)",
              cursor: "pointer",
              fontSize: 16,
              lineHeight: 1,
            }}
          >
            ×
          </button>
        </div>
      ))}
      {error && (
        <div role="alert" style={{ color: "var(--error)", fontSize: 12 }}>
          {error}
        </div>
      )}
      <div style={{ display: "flex", gap: 8 }}>
        <button type="button" onClick={addPort} style={btnStyle}>
          + Adicionar
        </button>
        <button type="button" onClick={() => setShowJson((s) => !s)} style={btnStyle}>
          Ver JSON
        </button>
      </div>
      {showJson && (
        <pre
          style={{
            margin: 0,
            padding: 12,
            background: "var(--bg-elevated)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)",
            fontSize: 12,
            color: "var(--text)",
            overflow: "auto",
          }}
        >
          {JSON.stringify(value.map(cleanPort), null, 2)}
        </pre>
      )}
    </div>
  );
}
