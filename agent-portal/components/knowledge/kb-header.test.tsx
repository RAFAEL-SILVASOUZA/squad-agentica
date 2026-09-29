import * as React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { KbHeader } from "./kb-header";
import { ToastProvider } from "@/components/ui/toast";

const mockPut = vi.fn();
const mockDelete = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    put: (...a: unknown[]) => mockPut(...a),
    delete: (...a: unknown[]) => mockDelete(...a),
  },
  ApiError: class ApiError extends Error {},
}));

const BASE = {
  id: "kb-1",
  name: "Base A",
  description: "Desc A",
  scope: "global",
  source: "upload",
  documentCount: 2,
  createdAt: "",
  updatedAt: "",
};

function renderHeader() {
  const onUpdated = vi.fn();
  const onDeleted = vi.fn();
  render(
    <ToastProvider>
      <KbHeader base={BASE} onUpdated={onUpdated} onDeleted={onDeleted} />
    </ToastProvider>
  );
  return { onUpdated, onDeleted };
}

describe("KbHeader", () => {
  beforeEach(() => vi.clearAllMocks());

  it("edita o nome e faz PUT só desse campo", async () => {
    mockPut.mockResolvedValue({ ...BASE, name: "Base B" });
    const { onUpdated } = renderHeader();
    fireEvent.click(screen.getByText("Base A"));
    const input = screen.getByLabelText("Nome da base");
    fireEvent.change(input, { target: { value: "Base B" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(mockPut).toHaveBeenCalledWith("/api/knowledge/kb-1", { name: "Base B" }));
    await waitFor(() => expect(onUpdated).toHaveBeenCalledWith(expect.objectContaining({ name: "Base B" })));
  });

  it("edita a descrição e faz PUT só desse campo", async () => {
    mockPut.mockResolvedValue({ ...BASE, description: "Nova" });
    renderHeader();
    fireEvent.click(screen.getByText("Desc A"));
    const input = screen.getByLabelText("Descrição da base");
    fireEvent.change(input, { target: { value: "Nova" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(mockPut).toHaveBeenCalledWith("/api/knowledge/kb-1", { description: "Nova" }));
  });

  it("recusa nome vazio com mensagem", () => {
    renderHeader();
    fireEvent.click(screen.getByText("Base A"));
    const input = screen.getByLabelText("Nome da base");
    fireEvent.change(input, { target: { value: "  " } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.getByRole("alert")).toHaveTextContent("Informe um nome para a base.");
    expect(mockPut).not.toHaveBeenCalled();
  });

  it("exclui a base após confirmação", async () => {
    mockDelete.mockResolvedValue(undefined);
    const { onDeleted } = renderHeader();
    fireEvent.click(screen.getByRole("button", { name: "Excluir base" }));
    const btns = await screen.findAllByRole("button", { name: "Excluir" });
    fireEvent.click(btns[btns.length - 1]);
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith("/api/knowledge/kb-1"));
    await waitFor(() => expect(onDeleted).toHaveBeenCalled());
  });
});
