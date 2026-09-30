import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { AppSidebar } from "./app-sidebar";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

describe("AppSidebar (Task 5)", () => {
  it("não tem mais o item 'Novo Agente'", () => {
    render(<AppSidebar />);
    expect(screen.queryByText("Novo Agente")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /\/agents\/new/ })
    ).not.toBeInTheDocument();
  });

  it("mostra 'Tools' em vez de 'Tools Custom'", () => {
    render(<AppSidebar />);
    expect(screen.getByText("Tools")).toBeInTheDocument();
    expect(screen.queryByText("Tools Custom")).not.toBeInTheDocument();
  });

  it("tem o grupo CONFIGURAÇÃO com 'Integrações' para /integrations", () => {
    render(<AppSidebar />);
    expect(screen.getByText("CONFIGURAÇÃO")).toBeInTheDocument();
    const integrations = screen.getByRole("link", { name: /Integrações/i });
    expect(integrations).toBeInTheDocument();
    expect(integrations).toHaveAttribute("href", "/integrations");
  });

  it("mantém os itens de navegação principais", () => {
    render(<AppSidebar />);
    expect(
      screen.getByRole("link", { name: /Dashboard/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Pipelines/i })
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Skills/i })).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Knowledge/i })
    ).toBeInTheDocument();
  });
});
