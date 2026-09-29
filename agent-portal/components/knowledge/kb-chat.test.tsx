import * as React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { KbChat } from "./kb-chat";
import { ToastProvider } from "@/components/ui/toast";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockDelete = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    get: (...a: unknown[]) => mockGet(...a),
    post: (...a: unknown[]) => mockPost(...a),
    delete: (...a: unknown[]) => mockDelete(...a),
  },
  ApiError: class ApiError extends Error {
    status: number;
    code: string;
    constructor(status: number, body: { error: string; code: string }) {
      super(body.error);
      this.status = status;
      this.code = body.code;
    }
  },
}));

import { ApiError } from "@/lib/api";

const CONVS = {
  items: [
    { id: "c2", title: "Sobre deploy", updatedAt: "2026-09-28T10:00:00Z", messageCount: 2 },
    { id: "c1", title: "Conversa antiga", updatedAt: "2026-09-27T10:00:00Z", messageCount: 2 },
  ],
};

const SOURCE = { documentId: "d1", documentName: "manual.pdf", chunkId: "ch1", text: "Trecho do manual", score: 0.876 };

function conv(id: string, title: string, q: string, a: string) {
  return {
    id,
    title,
    messages: [
      { id: `${id}-m1`, role: "user", content: q, sources: [], createdAt: "2026-09-28T10:00:00Z" },
      { id: `${id}-m2`, role: "assistant", content: a, sources: [SOURCE], createdAt: "2026-09-28T10:00:01Z" },
    ],
  };
}

function setup(convs: unknown = CONVS) {
  mockGet.mockImplementation(async (path: string) => {
    if (path.endsWith("/conversations")) return convs;
    if (path.endsWith("/conversations/c2")) return conv("c2", "Sobre deploy", "Como faço deploy?", "Use **docker compose**.");
    if (path.endsWith("/conversations/c1")) return conv("c1", "Conversa antiga", "Pergunta antiga", "Resposta antiga");
    throw new Error("unexpected " + path);
  });
}

function renderChat() {
  return render(
    <ToastProvider>
      <KbChat baseId="kb-1" />
    </ToastProvider>
  );
}

describe("KbChat", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setup();
  });

  it("carrega a conversa mais recente ao abrir e mostra fontes numeradas", async () => {
    renderChat();
    expect(await screen.findByText("Como faço deploy?")).toBeInTheDocument();
    expect(mockGet).toHaveBeenCalledWith("/api/knowledge/kb-1/conversations/c2");
    expect(screen.getByText("docker compose").tagName).toBe("STRONG");
    expect(screen.getByText(/1\. manual\.pdf/)).toBeInTheDocument();
    expect(screen.getByText(/0\.88/)).toBeInTheDocument();
    expect(screen.getByText("Trecho do manual")).toBeInTheDocument();
  });

  it("trocar de conversa carrega as mensagens dela", async () => {
    renderChat();
    await screen.findByText("Como faço deploy?");
    fireEvent.click(screen.getByRole("button", { name: /^Conversa antiga/ }));
    expect(await screen.findByText("Pergunta antiga")).toBeInTheDocument();
    expect(screen.queryByText("Como faço deploy?")).not.toBeInTheDocument();
  });

  it("perguntar mostra a resposta com fontes", async () => {
    setup({ items: [] });
    mockPost.mockImplementation(async (path: string) => {
      if (path.endsWith("/conversations")) return { id: "c9", title: "Nova conversa" };
      return { id: "m9", role: "assistant", content: "A resposta é 42", sources: [SOURCE] };
    });
    renderChat();
    const box = await screen.findByLabelText("Mensagem");
    fireEvent.change(box, { target: { value: "Qual a resposta?" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));
    expect(await screen.findByText("A resposta é 42")).toBeInTheDocument();
    expect(screen.getByText("Qual a resposta?")).toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith("/api/knowledge/kb-1/conversations/c9/messages", { content: "Qual a resposta?" });
    expect(screen.getByText(/1\. manual\.pdf/)).toBeInTheDocument();
  });

  it("Enter envia e Shift+Enter não envia", async () => {
    mockPost.mockResolvedValue({ id: "m9", role: "assistant", content: "ok", sources: [] });
    renderChat();
    await screen.findByText("Como faço deploy?");
    const box = screen.getByLabelText("Mensagem");
    fireEvent.change(box, { target: { value: "oi" } });
    fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
    expect(mockPost).not.toHaveBeenCalled();
    fireEvent.keyDown(box, { key: "Enter" });
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith("/api/knowledge/kb-1/conversations/c2/messages", { content: "oi" })
    );
  });

  it("mostra Pensando… e, em erro, recarrega e oferece Tentar de novo", async () => {
    let reject: (e: unknown) => void = () => {};
    mockPost.mockImplementationOnce(() => new Promise((_, r) => { reject = r; }));
    renderChat();
    await screen.findByText("Como faço deploy?");
    const box = screen.getByLabelText("Mensagem");
    fireEvent.change(box, { target: { value: "falha?" } });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(await screen.findByText("Pensando…")).toBeInTheDocument();
    reject(new ApiError(502, { error: "O modelo falhou.", code: "llm_error" }));
    expect(await screen.findByText("O modelo falhou.")).toBeInTheDocument();
    expect(screen.queryByText("Pensando…")).not.toBeInTheDocument();
    mockPost.mockResolvedValueOnce({ id: "m9", role: "assistant", content: "agora foi", sources: [] });
    fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    expect(await screen.findByText("agora foi")).toBeInTheDocument();
    expect(mockPost).toHaveBeenLastCalledWith("/api/knowledge/kb-1/conversations/c2/messages", { content: "falha?" });
  });

  it("exclui uma conversa após confirmação", async () => {
    mockDelete.mockResolvedValue(undefined);
    renderChat();
    await screen.findByText("Como faço deploy?");
    fireEvent.click(screen.getByRole("button", { name: "Excluir conversa Sobre deploy" }));
    fireEvent.click(await screen.findByRole("button", { name: "Excluir" }));
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith("/api/knowledge/kb-1/conversations/c2"));
  });
});
