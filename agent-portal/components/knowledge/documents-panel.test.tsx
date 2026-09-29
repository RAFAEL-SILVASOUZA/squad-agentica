import * as React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { DocumentsPanel } from "./documents-panel";
import { ToastProvider } from "@/components/ui/toast";

const mockList = vi.fn();
const mockPost = vi.fn();
const mockDelete = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    list: (...a: unknown[]) => mockList(...a),
    post: (...a: unknown[]) => mockPost(...a),
    delete: (...a: unknown[]) => mockDelete(...a),
  },
  ApiError: class ApiError extends Error {
    status: number;
    code: string;
    details?: Record<string, unknown>;
    constructor(status: number, body: { error: string; code: string; details?: Record<string, unknown> }) {
      super(body.error);
      this.status = status;
      this.code = body.code;
      this.details = body.details;
    }
  },
}));

import { ApiError } from "@/lib/api";

const DOCS = [
  { id: "d1", name: "manual.pdf", status: "ready", size: 10, chunkCount: 3, createdAt: "2026-09-26T10:00:00Z" },
  { id: "d2", name: "api.md", status: "ready", size: 10, chunkCount: 1, createdAt: "2026-09-26T10:00:00Z" },
];

function renderPanel(onCountChange = vi.fn()) {
  render(
    <ToastProvider>
      <DocumentsPanel baseId="kb-1" onCountChange={onCountChange} />
    </ToastProvider>
  );
  return onCountChange;
}

function pickFile(name = "manual.pdf") {
  const input = document.getElementById("knowledge-upload") as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(["x"], name)] } });
}

describe("DocumentsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockList.mockResolvedValue({ items: DOCS, total: 2, page: 1, limit: 100 });
  });

  it("lista os documentos da base", async () => {
    renderPanel();
    expect(await screen.findByText("manual.pdf")).toBeInTheDocument();
    expect(mockList).toHaveBeenCalledWith("/api/knowledge/kb-1/documents", { page: 1, limit: 100 });
  });

  it("envia arquivo e atualiza a contagem", async () => {
    mockPost.mockResolvedValue(undefined);
    const onCount = renderPanel();
    await screen.findByText("manual.pdf");
    pickFile("novo.md");
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith("/api/knowledge/kb-1/upload", expect.any(FormData)));
    await waitFor(() => expect(onCount).toHaveBeenCalledWith(2));
  });

  it("409 duplicate_document abre o modal e Substituir reenvia com replace", async () => {
    mockPost.mockRejectedValueOnce(
      new ApiError(409, { error: "dup", code: "duplicate_document", details: { documentId: "d1", name: "manual.pdf" } })
    );
    mockPost.mockResolvedValueOnce(undefined);
    renderPanel();
    await screen.findByText("manual.pdf");
    pickFile("copia.pdf");
    expect(await screen.findByText(/Este arquivo já existe nesta base como/)).toHaveTextContent("manual.pdf");
    fireEvent.click(screen.getByRole("button", { name: "Substituir" }));
    await waitFor(() =>
      expect(mockPost).toHaveBeenLastCalledWith("/api/knowledge/kb-1/upload?replace=d1", expect.any(FormData))
    );
  });

  it("Cancelar no modal de duplicado descarta o envio", async () => {
    mockPost.mockRejectedValueOnce(
      new ApiError(409, { error: "dup", code: "duplicate_document", details: { documentId: "d1", name: "manual.pdf" } })
    );
    renderPanel();
    await screen.findByText("manual.pdf");
    pickFile();
    await screen.findByText(/Este arquivo já existe/);
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    await waitFor(() => expect(screen.queryByText(/Este arquivo já existe/)).not.toBeInTheDocument());
    expect(mockPost).toHaveBeenCalledTimes(1);
  });

  it("remover documento pede confirmação e chama DELETE", async () => {
    mockDelete.mockResolvedValue(undefined);
    const onCount = renderPanel();
    await screen.findByText("manual.pdf");
    fireEvent.click(screen.getByRole("button", { name: "Remover manual.pdf" }));
    expect(mockDelete).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole("button", { name: "Remover" }));
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith("/api/knowledge/kb-1/documents/d1"));
    await waitFor(() => expect(screen.queryByText("manual.pdf")).not.toBeInTheDocument());
    expect(onCount).toHaveBeenCalledWith(1);
  });
});
