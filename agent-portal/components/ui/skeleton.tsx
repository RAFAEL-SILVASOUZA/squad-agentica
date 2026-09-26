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
}

export function Skeleton({
  width = "100%",
  height = 16,
  borderRadius = "var(--radius-sm)",
}: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
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
