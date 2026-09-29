"use client";

import * as React from "react";
import { AlertTriangle } from "lucide-react";
import type { ValidationError } from "@/components/flow/validation";

export interface ValidationTarget {
  nodeId?: string;
  edgeId?: string;
}

export interface ValidationListProps {
  errors: ValidationError[];
  onSelect: (target: ValidationTarget) => void;
}

/**
 * Lista dos erros de validação do grafo. Cada erro com nó ou aresta vira um
 * botão que seleciona o alvo no canvas.
 */
export function ValidationList({ errors, onSelect }: ValidationListProps) {
  return (
    <ul
      aria-label="Erros de validação"
      style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 4 }}
    >
      {errors.map((err, i) => {
        const target: ValidationTarget | null = err.nodeId
          ? { nodeId: err.nodeId }
          : err.edgeId
            ? { edgeId: err.edgeId }
            : null;
        const content = (
          <>
            <AlertTriangle size={12} aria-hidden="true" style={{ color: "var(--error)", flexShrink: 0 }} />
            <span>{err.message}</span>
          </>
        );
        const style: React.CSSProperties = {
          display: "flex",
          alignItems: "flex-start",
          gap: 6,
          width: "100%",
          padding: "6px 8px",
          fontSize: 12,
          textAlign: "left",
          color: "var(--text)",
          background: "transparent",
          border: "none",
          borderRadius: "var(--radius-sm)",
        };
        return (
          <li key={`${err.rule}-${i}`}>
            {target ? (
              <button type="button" onClick={() => onSelect(target)} style={{ ...style, cursor: "pointer" }}>
                {content}
              </button>
            ) : (
              <div style={style}>{content}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
