"use client";

import * as React from "react";
import { ChevronDown, ChevronRight, Download, FileText, FileDiff, Folder, FolderOpen, RefreshCw } from "lucide-react";
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
  /** Muda quando a lista deve ser recarregada (ex.: um nó terminou). */
  refreshKey?: number;
}

const STATUS_LABEL: Record<NonNullable<RunFile["status"]>, string> = {
  added: "novo",
  modified: "alterado",
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

interface DirNode {
  name: string;
  path: string;
  dirs: DirNode[];
  files: RunFile[];
  /** Arquivos alterados na subárvore. */
  changed: number;
}

/** Agrupa os caminhos em pastas: pastas antes, depois arquivos, em ordem alfabética. */
function buildTree(files: RunFile[]): DirNode {
  const root: DirNode = { name: "", path: "", dirs: [], files: [], changed: 0 };
  const index = new Map<string, DirNode>([["", root]]);
  for (const f of files) {
    const parts = f.path.split("/");
    let dir = root;
    for (let i = 0; i < parts.length - 1; i++) {
      const path = parts.slice(0, i + 1).join("/");
      let child = index.get(path);
      if (!child) {
        child = { name: parts[i], path, dirs: [], files: [], changed: 0 };
        index.set(path, child);
        dir.dirs.push(child);
      }
      if (f.status) dir.changed += 1;
      dir = child;
    }
    if (f.status) dir.changed += 1;
    dir.files.push(f);
  }
  const sort = (d: DirNode) => {
    d.dirs.sort((a, b) => a.name.localeCompare(b.name));
    d.files.sort((a, b) => a.path.localeCompare(b.path));
    d.dirs.forEach(sort);
  };
  sort(root);
  return root;
}

function baseName(path: string): string {
  return path.slice(path.lastIndexOf("/") + 1);
}

interface FileTreeProps {
  dir: DirNode;
  depth: number;
  isOpen: (dir: DirNode) => boolean;
  onToggle: (dir: DirNode) => void;
  selectedPath: string | null;
  onOpenFile: (file: RunFile) => void;
}

const rowButton: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 6,
  width: "100%",
  padding: "4px 8px",
  fontSize: 12,
  fontFamily: "var(--font-mono)",
  textAlign: "left",
  background: "none",
  border: "none",
  borderRadius: "var(--radius-sm)",
  cursor: "pointer",
};

function FileTreeItems({ dir, depth, isOpen, onToggle, selectedPath, onOpenFile }: FileTreeProps) {
  const indent = 8 + depth * 14;
  return (
    <>
      {dir.dirs.map((d) => {
        const open = isOpen(d);
        return (
          <li key={`d:${d.path}`}>
            <button
              type="button"
              onClick={() => onToggle(d)}
              aria-expanded={open}
              title={d.path}
              style={{ ...rowButton, paddingLeft: indent, color: "var(--text)" }}
            >
              {open ? (
                <ChevronDown size={12} aria-hidden="true" style={{ flexShrink: 0, color: "var(--text-muted)" }} />
              ) : (
                <ChevronRight size={12} aria-hidden="true" style={{ flexShrink: 0, color: "var(--text-muted)" }} />
              )}
              {open ? (
                <FolderOpen size={12} aria-hidden="true" style={{ flexShrink: 0, color: "var(--text-muted)" }} />
              ) : (
                <Folder size={12} aria-hidden="true" style={{ flexShrink: 0, color: "var(--text-muted)" }} />
              )}
              <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {d.name}
              </span>
              {d.changed > 0 && (
                <span style={{ flexShrink: 0, fontSize: 10, fontFamily: "var(--font)", color: "var(--warning)" }}>
                  {" "}
                  {d.changed} alterado(s)
                </span>
              )}
            </button>
            {open && (
              <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                <FileTreeItems
                  dir={d}
                  depth={depth + 1}
                  isOpen={isOpen}
                  onToggle={onToggle}
                  selectedPath={selectedPath}
                  onOpenFile={onOpenFile}
                />
              </ul>
            )}
          </li>
        );
      })}
      {dir.files.map((f) => (
        <li key={`f:${f.path}`}>
          <button
            type="button"
            onClick={() => onOpenFile(f)}
            aria-current={selectedPath === f.path ? "true" : undefined}
            aria-label={f.status ? `${f.path} — ${STATUS_LABEL[f.status]}` : f.path}
            title={f.path}
            style={{
              ...rowButton,
              paddingLeft: indent + 18,
              color: f.status === "deleted" ? "var(--text-muted)" : "var(--text)",
              background: selectedPath === f.path ? "var(--bg-hover)" : "none",
            }}
          >
            <FileText size={12} aria-hidden="true" style={{ flexShrink: 0, color: "var(--text-muted)" }} />
            <span
              style={{
                flex: 1,
                minWidth: 0,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                textDecoration: f.status === "deleted" ? "line-through" : undefined,
              }}
            >
              {baseName(f.path)}
            </span>
            {f.status && (
              <span style={{ flexShrink: 0, fontSize: 10, fontFamily: "var(--font)", color: STATUS_COLOR[f.status] }}>
                {STATUS_LABEL[f.status]}
              </span>
            )}
          </button>
        </li>
      ))}
    </>
  );
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
export function FilesTab({ runId, refreshKey }: FilesTabProps) {
  const [files, setFiles] = React.useState<RunFile[] | null>(null);
  const [listError, setListError] = React.useState<string | null>(null);
  const [filter, setFilter] = React.useState("");
  const [viewer, setViewer] = React.useState<Viewer>({ kind: "none" });
  const [downloading, setDownloading] = React.useState(false);
  const [downloadError, setDownloadError] = React.useState<string | null>(null);
  const [refreshing, setRefreshing] = React.useState(false);
  // Pastas abertas/fechadas pelo usuário; sem escolha, abre as que têm alterações.
  const [folderOpen, setFolderOpen] = React.useState<Record<string, boolean>>({});
  // Descarta respostas de um arquivo que já não está selecionado.
  const selectionRef = React.useRef(0);
  // Descarta listagens antigas (troca de run ou recarga sobreposta).
  const listRef = React.useRef(0);

  const loadList = React.useCallback(async () => {
    const token = ++listRef.current;
    setRefreshing(true);
    try {
      const res = await api.get<{ items: RunFile[] }>(`/api/runs/${runId}/files`);
      if (token === listRef.current) {
        setFiles(res.items);
        setListError(null);
      }
    } catch (err) {
      if (token === listRef.current) setListError(errorText(err, "Falha ao listar os arquivos."));
    } finally {
      if (token === listRef.current) setRefreshing(false);
    }
  }, [runId]);

  // Run novo: estado do zero.
  React.useEffect(() => {
    setFiles(null);
    setListError(null);
    setViewer({ kind: "none" });
    setFolderOpen({});
    void loadList();
  }, [loadList]);

  // Recarga pedida pelo monitor: mantém o arquivo aberto e as pastas.
  const lastRefreshKey = React.useRef(refreshKey);
  React.useEffect(() => {
    if (lastRefreshKey.current === refreshKey) return;
    lastRefreshKey.current = refreshKey;
    void loadList();
  }, [refreshKey, loadList]);

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

  const query = filter.trim().toLowerCase();
  const visible = React.useMemo(
    () => (files ?? []).filter((f) => !query || f.path.toLowerCase().includes(query)),
    [files, query]
  );
  const tree = React.useMemo(() => buildTree(visible), [visible]);
  // Filtrando, o caminho até cada resultado fica aberto.
  const isOpen = (d: DirNode) => (query ? true : folderOpen[d.path] ?? d.changed > 0);
  const toggleFolder = (d: DirNode) => {
    if (query) return;
    setFolderOpen((prev) => ({ ...prev, [d.path]: !(prev[d.path] ?? d.changed > 0) }));
  };
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
        <Button size="sm" onClick={() => void loadList()} loading={refreshing} aria-label="Atualizar arquivos">
          <RefreshCw size={13} aria-hidden="true" />
          Atualizar
        </Button>
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
            <FileTreeItems
              dir={tree}
              depth={0}
              isOpen={isOpen}
              onToggle={toggleFolder}
              selectedPath={selectedPath}
              onOpenFile={(f) => void openFile(f)}
            />
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
              ) : viewer.content?.tooLarge ? (
                <div style={notice}>Arquivo grande ({formatMb(viewer.content.size ?? viewer.file.size)} MB) — baixe o .zip</div>
              ) : viewer.content?.content == null ? (
                <div style={notice}>Conteúdo indisponível</div>
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
