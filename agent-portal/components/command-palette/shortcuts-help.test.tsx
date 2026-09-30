import * as React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

import { ShortcutsHelp } from "./shortcuts-help";

describe("ShortcutsHelp", () => {
  it("renderiza dialog 'Atalhos de teclado' quando open e nada quando fechado", () => {
    const { unmount } = render(<ShortcutsHelp open onClose={() => {}} />);
    expect(screen.getByRole("dialog", { name: "Atalhos de teclado" })).toBeInTheDocument();
    unmount();
    const { container } = render(<ShortcutsHelp open={false} onClose={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("lista os atalhos principais", () => {
    render(<ShortcutsHelp open onClose={() => {}} />);
    expect(screen.getByText("Ctrl / ⌘ + K")).toBeInTheDocument();
    // "Abrir a paleta de comandos" aparece 2x (Ctrl+K e "/").
    expect(screen.getAllByText("Abrir a paleta de comandos").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Mostrar esta ajuda")).toBeInTheDocument();
  });

  it("Esc fecha (chama onClose)", () => {
    const onClose = vi.fn();
    render(<ShortcutsHelp open onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
