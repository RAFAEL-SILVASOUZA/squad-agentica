import * as React from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

const createPipelineAndNavigate = vi.fn();
vi.mock("@/lib/create-pipeline", () => ({
  useCreatePipelineAndNavigate: () => createPipelineAndNavigate,
}));

const groups = [
  {
    type: "agents",
    label: "Agentes",
    items: [{ id: "a1", name: "Redator de Especificações", type: "agents", href: "/agents/a1" }],
  },
  {
    type: "pipelines",
    label: "Pipelines",
    items: [{ id: "p1", name: "Build", type: "pipelines", href: "/pipelines/p1" }],
  },
];
vi.mock("./use-palette-data", () => ({
  usePaletteData: () => ({ groups, loading: false }),
}));

import { CommandPalette } from "./command-palette";

function getInput() {
  return screen.getByRole("dialog", { name: "Buscar" }).querySelector("input") as HTMLInputElement;
}

describe("CommandPalette", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    push.mockClear();
    createPipelineAndNavigate.mockClear();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renderiza dialog 'Buscar' quando open e nada quando fechado", () => {
    const { unmount } = render(<CommandPalette open onClose={() => {}} />);
    expect(screen.getByRole("dialog", { name: "Buscar" })).toBeInTheDocument();
    unmount();
    const { container } = render(<CommandPalette open={false} onClose={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("'especif' encontra 'Redator de Especificações' (sem acento) e Enter navega para /agents/a1", () => {
    render(<CommandPalette open onClose={() => {}} />);
    const input = getInput();
    fireEvent.change(input, { target: { value: "especif" } });
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(screen.getByText("Redator de Especificações")).toBeInTheDocument();
    expect(screen.queryByText("Build")).not.toBeInTheDocument();
    // O item do agente é a 4ª linha (após as 3 ações fixas).
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(push).toHaveBeenCalledWith("/agents/a1");
  });

  it("sem resultados mostra 'Nada encontrado' e mantém as ações de criar", () => {
    render(<CommandPalette open onClose={() => {}} />);
    const input = getInput();
    fireEvent.change(input, { target: { value: "zzz" } });
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(screen.getByText("Nada encontrado para 'zzz'")).toBeInTheDocument();
    expect(screen.getByText("Novo agente")).toBeInTheDocument();
    expect(screen.getByText("Nova pipeline")).toBeInTheDocument();
    expect(screen.getByText("Nova base")).toBeInTheDocument();
  });
});
