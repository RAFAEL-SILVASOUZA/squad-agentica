import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Breadcrumb } from "./breadcrumb";

describe("Breadcrumb (Task 5)", () => {
  it("renders 'Pipelines / Nome' with the last item as current page", () => {
    render(
      <Breadcrumb
        items={[
          { label: "Pipelines", href: "/pipelines" },
          { label: "Nome" },
        ]}
      />
    );

    const nav = screen.getByRole("navigation", { name: "Você está em" });
    expect(nav).toBeInTheDocument();

    // "Pipelines" é um link que aponta para /pipelines.
    const pipelinesLink = screen.getByRole("link", { name: "Pipelines" });
    expect(pipelinesLink).toHaveAttribute("href", "/pipelines");

    // "Nome" é a página atual: NÃO é link e tem aria-current="page".
    const current = screen.getByText("Nome");
    expect(current).toHaveAttribute("aria-current", "page");
    expect(current).not.toHaveAttribute("href");
    expect(pipelinesLink).not.toBe(current);
  });

  it("não renderiza link para o último item", () => {
    render(
      <Breadcrumb
        items={[
          { label: "Agentes", href: "/agents" },
          { label: "Meu agente" },
        ]}
      />
    );

    // Só existe um link (o "Agentes"); o atual não é link.
    expect(screen.getAllByRole("link")).toHaveLength(1);
    expect(screen.getByText("Meu agente")).toHaveAttribute("aria-current", "page");
  });
});
