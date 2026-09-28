"use client";

import * as React from "react";
import { Download, FileText, FileDiff, Folder } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";

export interface RunFile {
  path: string;
  size: number;
  binary: boolean;
  status: "added" | "modified" | "deleted" | null;
}

interface FileContent {
  path: string;
  content: string | null;
  binary: boolean;
  tooLarge: boolean;
  size: number;
}

export interface FilesTabProps {
  runId: string;
}

const STATUS_LABEL: Record<NonNullable<RunFile["status"]>, string> = {
  added: "adicionado",
  modified: "modificado",
  deleted: "removido",
};

const STATUS_COLOR: Record<NonNullable<RunFile["status"]>, string> = {
  added: "var(--success)",
  modified: "var(--warning)",
  deleted: "var(--error)",
};

function formatMb(bytes: number): string {
  return (bytes / (1024 * 1024)).toLocaleString("pt-BR", { maximumFractionDigits: 1 });
}

function errorText(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback;
}

/** Salva um Blob como arquivo (link temporário com `download`). */
function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

type Viewer =
  | { kind: "none" }
  | { kind: "file"; file: RunFile; loading: boolean; content?: FileContent; error?: string }
  | { kind: "diff"; loading: boolean; diff?: string; truncated?: boolean; error?: string };

const notice: React.CSSProperties = {
  padding: "12px 14px",
  fontSize: 12,
  color: "var(--text-secondary)",
  background: "var(--bg-elevated)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-sm)",
};

const codeBlock: React.CSSProperties = {
  margin: 0,
  padding: 12,
  fontFamily: "var(--font-mono)",
  fontSize: 12,
  lineHeight: 1.55,
  color: "var(--text)",
  background: "var(--bg-elevated)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-sm)",
  overflow: "auto",
  maxHeight: "70vh",
  whiteSpace: "pre",
};

/**
 * Aba "Arquivos do projeto": árvore do workspace do run com o status de cada
 * arquivo (adicionado/modificado/removido), visualização de texto, diff e
 * download do .zip. Binários e arquivos grandes não são exibidos.
 */
export function FilesTab({ runId }: FilesTabProps) {
  const [files, setFiles] = React.useState<RunFile[] | null>(null);
  const [listError, setListError] = React.useState<string | null>(null);
  const [filter, setFilter] = React.useState("");
  const [viewer, setViewer] = React.useState<Viewer>({ kind: "none" });
  const [downloading, setDownloading] = React.useState(false);
  const [downloadError, setDownloadError] = React.useState<string | null>(null);
  // Descarta respostas de um arquivo que já não está selecionado.
  const selectionRef = React.useRef(0);

  React.useEffect(() => {
    let cancelled = false;
    setFiles(null);
    setListError(null);
    setViewer({ kind: "none" });
    api
      .get<{ items: RunFile[] }>(`/api/runs/${runId}/files`)
      .then((res) => {
        if (!cancelled) setFiles([...res.items].sort((a, b) => a.path.localeCompare(b.path)));
      })
      .catch((err) => {
        if (!cancelled) setListError(errorText(err, "Falha ao listar os arquivos."));
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  const openFile = async (file: RunFile) => {
    const token = ++selectionRef.current;
    // Binário e removido: nada a buscar.
    if (file.binary || file.status === "deleted") {
      setViewer({ kind: "file", file, loading: false });
      return;
    }
    setViewer({ kind: "file", file, loading: true });
    try {
      const content = await api.get<FileContent>(`/api/runs/${runId}/files/content`, {
        query: { path: file.path },
      });
      if (token === selectionRef.current) setViewer({ kind: "file", file, loading: false, content });
    } catch (err) {
      if (token === selectionRef.current) {
        setViewer({ kind: "file", file, loading: false, error: errorText(err, "Falha ao abrir o arquivo.") });
      }
    }
  };

  const openDiff = async () => {
    const token = ++selectionRef.current;
    setViewer({ kind: "diff", loading: true });
    try {
      const res = await api.get<{ diff: string; truncated: boolean }>(`/api/runs/${runId}/diff`);
      if (token === selectionRef.current) {
        setViewer({ kind: "diff", loading: false, diff: res.diff, truncated: res.truncated });
      }
    } catch (err) {
      if (token === selectionRef.current) {
        setViewer({ kind: "diff", loading: false, error: errorText(err, "Falha ao carregar o diff.") });
      }
    }
  };

  const downloadZip = async () => {
    setDownloading(true);
    setDownloadError(null);
    try {
      const { blob, filename } = await api.download(`/api/runs/${runId}/archive`);
      saveBlob(blob, filename ?? `run-${runId.slice(0, 8)}.zip`);
    } catch (err) {
      setDownloadError(errorText(err, "Falha ao baixar o .zip."));
    } finally {
      setDownloading(false);
    }
  };

  const visible = React.useMemo(() => {
    const q = filter.trim().toLowerCase();
    return (files ?? []).filter((f) => !q || f.path.toLowerCase().includes(q));
  }, [files, filter]);
  const changedCount = (files ?? []).filter((f) => f.status).length;

  const selectedPath = viewer.kind === "file" ? viewer.file.path : null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 12, color: "var(--text-secondary)", flex: 1, minWidth: 160 }}>
          {files
            ? `${files.length} arquivo(s) no projeto · ${changedCount} alterado(s) nesta execução`
            : "Carregando arquivos…"}
        </span>
        <Button size="sm" onClick={() => void openDiff()} aria-pressed={viewer.kind === "diff"}>
          <FileDiff size={13} aria-hidden="true" />
          Ver diff
        </Button>
        <Button size="sm" onClick={() => void downloadZip()} loading={downloading}>
          <Download size={13} aria-hidden="true" />
          Baixar .zip
        </Button>
      </div>

      {downloadError && (
        <div role="alert" style={{ ...notice, borderColor: "var(--error)", color: "var(--error)" }}>
          {downloadError}
        </div>
      )}
      {listError && (
        <div role="alert" style={{ ...notice, borderColor: "var(--error)", color: "var(--error)" }}>
          {listError}
        </div>
      )}

      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-start" }}>
        {/* Lista de arquivos */}
        <div
          style={{
            flex: "1 1 260px",
            maxWidth: "100%",
            minWidth: 0,
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          <Input
            aria-label="Filtrar arquivos"
            placeholder="Filtrar arquivos…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <ul
            aria-label="Arquivos do projeto"
            style={{
              listStyle: "none",
              margin: 0,
              padding: 4,
              maxHeight: "70vh",
              overflowY: "auto",
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-sm)",
            }}
          >
            {files && visible.length === 0 && (
              <li style={{ padding: 8, fontSize: 12, color: "var(--text-muted)" }}>
                {files.length === 0 ? "Nenhum arquivo nesta execução." : "Nenhum arquivo corresponde ao filtro."}
              </li>
            )}
            {visible.map((f) => (
              <li key={f.path}>
                <button
                  type="button"
                  onClick={() => void openFile(f)}
                  aria-current={selectedPath === f.path ? "true" : undefined}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    width: "100%",
                    padding: "5px 8px",
                    fontSize: 12,
                    fontFamily: "var(--font-mono)",
                    textAlign: "left",
                    color: f.status === "deleted" ? "var(--text-muted)" : "var(--text)",
                    textDecoration: f.status === "deleted" ? "line-through" : undefined,
                    background: selectedPath === f.path ? "var(--bg-hover)" : "none",
                    border: "none",
                    borderRadius: "var(--radius-sm)",
                    cursor: "pointer",
                  }}
                >
                  <FileText size={12} aria-hidden="true" style={{ flexShrink: 0, color: "var(--text-muted)" }} />
                  <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {f.path}
                  </span>
                  {f.status && (
                    <span
                      style={{
                        flexShrink: 0,
                        fontSize: 10,
                        fontFamily: "var(--font)",
                        color: STATUS_COLOR[f.status],
                        textDecoration: "none",
                      }}
                    >
                      {STATUS_LABEL[f.status]}
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        </div>

        {/* Visualizador */}
        <div style={{ flex: "999 1 420px", minWidth: 0, display: "flex", flexDirection: "column", gap: 8 }}>
          {viewer.kind === "none" && (
            <div style={{ ...notice, display: "flex", alignItems: "center", gap: 8 }}>
              <Folder size={14} aria-hidden="true" />
              Selecione um arquivo para ver o conteúdo, ou veja o diff das alterações.
            </div>
          )}

          {viewer.kind === "file" && (
            <>
              <div style={{ fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>
                {viewer.file.path}
              </div>
              {viewer.file.binary ? (
                <div style={notice}>Arquivo binário — baixe o .zip</div>
              ) : viewer.file.status === "deleted" ? (
                <div style={notice}>Arquivo removido nesta execução.</div>
              ) : viewer.loading ? (
                <div style={notice}>Carregando…</div>
              ) : viewer.error ? (
                <div role="alert" style={{ ...notice, color: "var(--error)" }}>
                  {viewer.error}
                </div>
              ) : viewer.content?.binary ? (
                <div style={notice}>Arquivo binário — baixe o .zip</div>
              ) : viewer.content?.tooLarge || viewer.content?.content == null ? (
                <div style={notice}>Arquivo grande ({formatMb(viewer.content?.size ?? viewer.file.size)} MB) — baixe o .zip</div>
              ) : (
                <pre style={codeBlock}>{viewer.content.content}</pre>
              )}
            </>
          )}

          {viewer.kind === "diff" &&
            (viewer.loading ? (
              <div style={notice}>Carregando diff…</div>
            ) : viewer.error ? (
              <div role="alert" style={{ ...notice, color: "var(--error)" }}>
                {viewer.error}
              </div>
            ) : (
              <>
                {viewer.truncated && (
                  <div style={{ ...notice, borderColor: "var(--warning)" }}>
                    Diff truncado — baixe o .zip para ver tudo
                  </div>
                )}
                {viewer.diff ? (
                  <pre style={codeBlock}>
                    {viewer.diff.split("\n").map((line, i) => (
                      <span
                        key={i}
                        style={{
                          display: "block",
                          color: line.startsWith("+") && !line.startsWith("+++")
                            ? "var(--success)"
                            : line.startsWith("-") && !line.startsWith("---")
                              ? "var(--error)"
                              : line.startsWith("@@")
                                ? "var(--info)"
                                : undefined,
                        }}
                      >
                        {line || " "}
                      </span>
                    ))}
                  </pre>
                ) : (
                  <div style={notice}>Nenhuma alteração nesta execução.</div>
                )}
              </>
            ))}
        </div>
      </div>
    </div>
  );
}
