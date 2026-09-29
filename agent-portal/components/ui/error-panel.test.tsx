import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ErrorPanel } from "./error-panel";

describe("ErrorPanel", () => {
  it("mostra impacto, detalhes recolhidos e tentar de novo", async () => {
    const onRetry = vi.fn();
    render(
      <ErrorPanel
        title="Não foi possível salvar o agente"
        detail="HTTP 404 · POST /api/agents/chat/confirm"
        onRetry={onRetry}
      />
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Não foi possível salvar o agente"
    );
    expect(screen.queryByText(/HTTP 404/)).not.toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Ver detalhes" }));
    expect(screen.getByText(/HTTP 404/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("mostra botão de copiar detalhes e não quebra sem onRetry", async () => {
    const { container } = render(
      <ErrorPanel title="Algo deu errado" detail="detalhe técnico" />
    );
    // Sem onRetry não aparece ação de recuperação
    expect(
      screen.queryByRole("button", { name: "Tentar de novo" })
    ).not.toBeInTheDocument();
    // "Copiar detalhes" está disponível quando há detail
    const copyBtn = screen.getByRole("button", { name: "Copiar detalhes" });
    expect(copyBtn).toBeInTheDocument();
    // jsdom não implementa clipboard: mockamos e validamos o texto copiado
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    fireEvent.click(copyBtn);
    expect(writeText).toHaveBeenCalledWith("detalhe técnico");
    vi.unstubAllGlobals();
    expect(container).toHaveTextContent("Algo deu errado");
  });
});
