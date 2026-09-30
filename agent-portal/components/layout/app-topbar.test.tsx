import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { AppTopbar } from "./app-topbar";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
}));

vi.mock("next-auth/react", () => ({
  useSession: () => ({
    data: { user: { name: "Test User" } },
    status: "authenticated",
  }),
  signOut: vi.fn(),
}));

const { trigger } = vi.hoisted(() => ({
  trigger: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("@/lib/create-pipeline", () => ({
  useCreatePipelineAndNavigate: vi.fn(() => trigger),
}));

describe("AppTopbar (Task 5)", () => {
  it("tem o botão '+ Novo' que abre um menu com Agente, Pipeline e Base de conhecimento", () => {
    render(<AppTopbar />);

    const novo = screen.getByRole("button", { name: /novo/i });
    expect(novo).toBeInTheDocument();

    // Menu fechado: os itens não estão visíveis.
    expect(screen.queryByText("Agente")).not.toBeInTheDocument();
    expect(screen.queryByText("Pipeline")).not.toBeInTheDocument();
    expect(screen.queryByText("Base de conhecimento")).not.toBeInTheDocument();

    // Abre o menu.
    fireEvent.click(novo);
    expect(novo).toHaveAttribute("aria-expanded", "true");

    // Itens do menu presentes e localizáveis (role="menuitem").
    const agente = screen.getByRole("menuitem", { name: "Agente" });
    expect(agente).toHaveAttribute("href", "/agents/new");

    const base = screen.getByRole("menuitem", { name: "Base de conhecimento" });
    expect(base).toHaveAttribute("href", "/knowledge?new=1");

    // "Pipeline" dispara a criação (botão, não link).
    const pipelineItem = screen.getByRole("menuitem", { name: "Pipeline" });
    expect(pipelineItem).toBeInTheDocument();
  });

  it("cria a pipeline e navega para /pipelines/<id>?new=1 ao clicar em Pipeline", async () => {
    const { useCreatePipelineAndNavigate } = await import("@/lib/create-pipeline");
    render(<AppTopbar />);

    const novo = screen.getByRole("button", { name: /novo/i });
    fireEvent.click(novo);
    fireEvent.click(screen.getByRole("menuitem", { name: "Pipeline" }));

    // O hook é chamado em cada render; o que importa é que a função devolvida
    // (que dispara POST + navegação) foi chamada uma vez ao clicar em Pipeline.
    expect(useCreatePipelineAndNavigate).toHaveBeenCalled();
    expect(trigger).toHaveBeenCalledTimes(1);
  });

  it("não tem mais a engrenagem de Integrações", () => {
    render(<AppTopbar />);
    // A engrenagem (Settings) de Integrações saiu da topbar; o toggle de tema
    // ainda usa o mesmo ícone (Sun/Moon), então verificamos pelo aria-label.
    expect(
      screen.queryByRole("link", { name: "Integrações" })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Integrações" })
    ).not.toBeInTheDocument();
  });
});
