import * as React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { FilesTab } from "./files-tab";

const mockGet = vi.fn();
const mockDownload = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    get: (...args: unknown[]) => mockGet(...args),
    download: (...args: unknown[]) => mockDownload(...args),
  },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, body: { error: string; code: string }) {
      super(body.error);
      this.status = status;
    }
  },
}));

describe("FilesTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("lists files with status, opens text, marks binary and offers zip", async () => {
    mockGet.mockImplementation(async (p: string) =>
      p.endsWith("/files")
        ? {
            items: [
              { path: "src/a.py", size: 9, binary: false, status: "added" },
              { path: "logo.png", size: 5, binary: true, status: "added" },
            ],
          }
        : { path: "src/a.py", content: "print(1)", binary: false, tooLarge: false, size: 9 }
    );
    render(<FilesTab runId="r1" />);
    fireEvent.click(await screen.findByRole("button", { name: /src\/a\.py/ }));
    expect(await screen.findByText("print(1)")).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith("/api/runs/r1/files/content", { query: { path: "src/a.py" } });
    fireEvent.click(screen.getByRole("button", { name: /logo\.png/ }));
    expect(screen.getByText(/Arquivo binário/)).toBeInTheDocument();
    // Binário não é buscado nem renderizado.
    expect(mockGet).not.toHaveBeenCalledWith("/api/runs/r1/files/content", { query: { path: "logo.png" } });
    expect(screen.getByRole("button", { name: /Baixar \.zip/ })).toBeInTheDocument();
  });

  it("renders a tree: folders first, collapsible, with changed counts; filter shows nested matches", async () => {
    mockGet.mockResolvedValue({
      items: [
        { path: "README.md", size: 1, binary: false, status: null },
        { path: "src/app/main.py", size: 1, binary: false, status: "modified" },
        { path: "src/app/util.py", size: 1, binary: false, status: "added" },
        { path: "src/lib/x.py", size: 1, binary: false, status: null },
        { path: "docs/guia.md", size: 1, binary: false, status: null },
      ],
    });
    render(<FilesTab runId="r1" />);
    const src = await screen.findByRole("button", { name: /^src( |$)/ });
    // Pasta com alterações vem aberta e mostra a contagem.
    expect(src).toHaveAttribute("aria-expanded", "true");
    expect(src).toHaveAccessibleName(/2 alterado/);
    // Pastas antes de arquivos, em ordem alfabética.
    const tree = screen.getByRole("list", { name: "Arquivos do projeto" });
    const top = Array.from(tree.children).map((li) => li.querySelector("button")?.textContent ?? "");
    expect(top[0]).toMatch(/^docs( |$)/);
    expect(top[1]).toMatch(/^src( |$)/);
    expect(top[2]).toMatch(/README\.md/);
    // Status nos arquivos.
    expect(screen.getByRole("button", { name: /src\/app\/main\.py.*alterado/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /src\/app\/util\.py.*novo/ })).toBeInTheDocument();
    // Pasta sem alterações vem fechada.
    expect(screen.getByRole("button", { name: /^docs( |$)/ })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: /docs\/guia\.md/ })).not.toBeInTheDocument();

    // Recolher a pasta esconde os filhos.
    fireEvent.click(src);
    expect(src).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("button", { name: /src\/app\/main\.py/ })).not.toBeInTheDocument();

    // Filtro mostra o arquivo aninhado com o caminho aberto.
    fireEvent.change(screen.getByLabelText("Filtrar arquivos"), { target: { value: "guia" } });
    expect(screen.getByRole("button", { name: /docs\/guia\.md/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /README/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^src( |$)/ })).not.toBeInTheDocument();
  });

  it("refreshes the list (button or refreshKey) without closing the open file", async () => {
    let items = [{ path: "a.txt", size: 1, binary: false, status: "added" }];
    mockGet.mockImplementation(async (p: string) =>
      p.endsWith("/files") ? { items } : { path: "a.txt", content: "conteudo A", binary: false, tooLarge: false, size: 1 }
    );
    const { rerender } = render(<FilesTab runId="r1" refreshKey={0} />);
    fireEvent.click(await screen.findByRole("button", { name: /a\.txt/ }));
    expect(await screen.findByText("conteudo A")).toBeInTheDocument();

    items = [...items, { path: "b.txt", size: 1, binary: false, status: "added" }];
    rerender(<FilesTab runId="r1" refreshKey={1} />);
    expect(await screen.findByRole("button", { name: /b\.txt/ })).toBeInTheDocument();
    expect(screen.getByText("conteudo A")).toBeInTheDocument();

    items = [...items, { path: "c.txt", size: 1, binary: false, status: "added" }];
    fireEvent.click(screen.getByRole("button", { name: "Atualizar arquivos" }));
    expect(await screen.findByRole("button", { name: /c\.txt/ })).toBeInTheDocument();
    expect(screen.getByText("conteudo A")).toBeInTheDocument();
  });

  it("says content unavailable when the server sends no content but it is not too large", async () => {
    mockGet.mockImplementation(async (p: string) =>
      p.endsWith("/files")
        ? { items: [{ path: "x.txt", size: 10, binary: false, status: "added" }] }
        : { path: "x.txt", content: null, binary: false, tooLarge: false, size: 10 }
    );
    render(<FilesTab runId="r1" />);
    fireEvent.click(await screen.findByRole("button", { name: /x\.txt/ }));
    expect(await screen.findByText("Conteúdo indisponível")).toBeInTheDocument();
    expect(screen.queryByText(/Arquivo grande/)).not.toBeInTheDocument();
  });

  it("shows the size of a file too large to preview", async () => {
    mockGet.mockImplementation(async (p: string) =>
      p.endsWith("/files")
        ? { items: [{ path: "dump.sql", size: 3 * 1024 * 1024, binary: false, status: "modified" }] }
        : { path: "dump.sql", content: null, binary: false, tooLarge: true, size: 3 * 1024 * 1024 }
    );
    render(<FilesTab runId="r1" />);
    fireEvent.click(await screen.findByRole("button", { name: /dump\.sql/ }));
    expect(await screen.findByText(/Arquivo grande \(3(,0)? MB\) — baixe o \.zip/)).toBeInTheDocument();
  });

  it("downloads the zip with the session token and saves it with the server filename", async () => {
    mockGet.mockResolvedValue({ items: [] });
    const blob = new Blob(["PK"]);
    mockDownload.mockResolvedValue({ blob, filename: "pipe-abc.zip" });
    const createObjectURL = vi.fn(() => "blob:zip");
    const revokeObjectURL = vi.fn();
    Object.assign(URL, { createObjectURL, revokeObjectURL });
    const clicked: HTMLAnchorElement[] = [];
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        clicked.push(this);
      });

    render(<FilesTab runId="r1" />);
    fireEvent.click(await screen.findByRole("button", { name: /Baixar \.zip/ }));

    await waitFor(() => expect(mockDownload).toHaveBeenCalledWith("/api/runs/r1/archive"));
    await waitFor(() => expect(clicked).toHaveLength(1));
    expect(createObjectURL).toHaveBeenCalledWith(blob);
    expect(clicked[0].download).toBe("pipe-abc.zip");
    expect(clicked[0].getAttribute("href")).toBe("blob:zip");
    clickSpy.mockRestore();
  });

  it("shows the API error when the workspace was purged", async () => {
    const { ApiError } = await import("@/lib/api");
    mockGet.mockResolvedValue({ items: [] });
    mockDownload.mockRejectedValue(new ApiError(404, { error: "Arquivos removidos", code: "workspace_not_found" }));
    render(<FilesTab runId="r1" />);
    expect(await screen.findByText(/Nenhum arquivo/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Baixar \.zip/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Arquivos removidos");
  });

  it("shows the diff and warns when it was truncated", async () => {
    mockGet.mockImplementation(async (p: string) =>
      p.endsWith("/files")
        ? { items: [{ path: "a.txt", size: 1, binary: false, status: "modified" }] }
        : { diff: "diff --git a/a.txt b/a.txt\n+novo", truncated: true }
    );
    render(<FilesTab runId="r1" />);
    fireEvent.click(await screen.findByRole("button", { name: /Ver diff/ }));
    expect(await screen.findByText(/\+novo/)).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith("/api/runs/r1/diff");
    expect(screen.getByText("Diff truncado — baixe o .zip para ver tudo")).toBeInTheDocument();
  });
});
