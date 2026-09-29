"use client";

import * as React from "react";

/**
 * Skeleton (design system §2.18).
 * Bloco com animação de shimmer. Altura proporcional ao elemento.
 */
export interface SkeletonProps {
  width?: number | string;
  height?: number | string;
  borderRadius?: number | string;
  /** Identificador opcional (ex.: "header"), exposto em data-skeleton. */
  label?: string;
}

export function Skeleton({
  width = "100%",
  height = 16,
  borderRadius = "var(--radius-sm)",
  label,
}: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      data-skeleton={label}
      style={{
        width,
        height,
        borderRadius,
        background: "var(--bg-hover)",
        backgroundImage:
          "linear-gradient(90deg, var(--bg-hover) 0%, var(--bg-card) 50%, var(--bg-hover) 100%)",
        backgroundSize: "400px 100%",
        animation: "shimmer 1.5s ease-in-out infinite",
      }}
    />
  );
}

/**
 * Lista de linhas skeleton (tabelas, feeds). `rows` linhas de altura uniforme.
 */
export interface SkeletonRowsProps {
  rows?: number;
  height?: number;
  gap?: number;
}

export function SkeletonRows({ rows = 4, height = 40, gap = 10 }: SkeletonRowsProps) {
  return (
    <div aria-hidden="true" style={{ display: "flex", flexDirection: "column", gap }}>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} label="row" height={height} />
      ))}
    </div>
  );
}

/**
 * Esqueleto de página inteira: cabeçalho, bloco de linhas e bloco de rodapé.
 * Usar enquanto o conteúdo real carrega, antes de exibir a lista/detalhe.
 */
export interface SkeletonShellProps {
  rows?: number;
}

export function SkeletonShell({ rows = 4 }: SkeletonShellProps) {
  return (
    <div aria-hidden="true" style={{ display: "flex", flexDirection: "column", gap: "16px", padding: "8px" }}>
      <Skeleton label="header" height={32} width="40%" />
      <SkeletonRows rows={rows} height={56} gap={12} />
      <Skeleton label="footer" height={24} width="25%" />
    </div>
  );
}
