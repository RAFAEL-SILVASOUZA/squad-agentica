"use client";

import * as React from "react";
import { Drawer } from "@/components/ui/drawer";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * DocumentDrawer: painel lateral com detalhes de um documento.
 * Mostra nome, tamanho, status, chunkCount e preview dos primeiros chunks.
 */
export interface DocumentDetail {
  id: string;
  name: string;
  size: number;
  status: string;
  chunkCount: number;
  createdAt: string;
  preview: string[];
}

export interface DocumentDrawerProps {
  open: boolean;
  onClose: () => void;
  document: DocumentDetail | null;
  loading?: boolean;
  error?: string | null;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function DocumentDrawer({ open, onClose, document, loading, error }: DocumentDrawerProps) {
  if (!open) return null;

  return (
    <Drawer open={open} onClose={onClose} title={document?.name ?? "Documento"} width={360}>
      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <Skeleton width="60%" height={16} />
          <Skeleton width="40%" height={12} />
          <Skeleton width="100%" height={80} />
        </div>
      ) : error ? (
        <div style={{ padding: "8px 0" }}>
          <p style={{ fontSize: 13, color: "var(--error)", margin: 0 }}>{error}</p>
        </div>
      ) : document ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Metadados */}
          <div style={{ display: "flex", gap: 16, fontSize: 12, color: "var(--text-secondary)" }}>
            <span>{formatSize(document.size)}</span>
            <span>{document.status}</span>
            <span>{document.chunkCount} trechos</span>
          </div>

          {/* Preview dos chunks */}
          {document.preview.length > 0 && (
            <div>
              <h3 style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px", margin: "0 0 8px" }}>
                Trechos
              </h3>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {document.preview.map((chunk, i) => (
                  <div
                    key={i}
                    style={{
                      fontSize: 12,
                      color: "var(--text)",
                      background: "var(--bg-card)",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "var(--radius-sm)",
                      padding: "8px 10px",
                      whiteSpace: "pre-wrap",
                      overflow: "hidden",
                    }}
                  >
                    <span style={{ color: "var(--text-muted)", fontSize: 10, display: "block", marginBottom: 4 }}>
                      Trecho {i + 1}
                    </span>
                    {chunk}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <p style={{ fontSize: 13, color: "var(--text-muted)" }}>Documento não encontrado.</p>
      )}
    </Drawer>
  );
}
