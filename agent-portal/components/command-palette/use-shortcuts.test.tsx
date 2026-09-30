import { render, renderHook, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { useShortcuts } from "./use-shortcuts";

describe("useShortcuts", () => {
  it("chama onPalette ao pressionar Ctrl+K", () => {
    const onPalette = vi.fn();
    const onHelp = vi.fn();
    renderHook(() => useShortcuts({ onPalette, onHelp }));
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(onPalette).toHaveBeenCalledTimes(1);
    expect(onHelp).not.toHaveBeenCalled();
  });

  it("chama onPalette ao pressionar ⌘K (metaKey)", () => {
    const onPalette = vi.fn();
    const onHelp = vi.fn();
    renderHook(() => useShortcuts({ onPalette, onHelp }));
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    expect(onPalette).toHaveBeenCalledTimes(1);
  });

  it("chama onPalette com Ctrl+K mesmo com foco em um input", () => {
    const onPalette = vi.fn();
    const onHelp = vi.fn();
    renderHook(() => useShortcuts({ onPalette, onHelp }));
    const { container } = render(<input aria-label="campo" />);
    const input = container.querySelector("input")!;
    fireEvent.keyDown(input, { key: "k", ctrlKey: true });
    expect(onPalette).toHaveBeenCalledTimes(1);
  });

  it("não chama onPalette para '/' com foco em um input", () => {
    const onPalette = vi.fn();
    const onHelp = vi.fn();
    renderHook(() => useShortcuts({ onPalette, onHelp }));
    const { container } = render(<input aria-label="campo" />);
    const input = container.querySelector("input")!;
    fireEvent.keyDown(input, { key: "/" });
    expect(onPalette).not.toHaveBeenCalled();
  });

  it("chama onPalette para '/' com foco no body", () => {
    const onPalette = vi.fn();
    const onHelp = vi.fn();
    renderHook(() => useShortcuts({ onPalette, onHelp }));
    fireEvent.keyDown(window, { key: "/" });
    expect(onPalette).toHaveBeenCalledTimes(1);
  });

  it("chama onHelp para '?' com foco no body", () => {
    const onPalette = vi.fn();
    const onHelp = vi.fn();
    renderHook(() => useShortcuts({ onPalette, onHelp }));
    fireEvent.keyDown(window, { key: "?" });
    expect(onHelp).toHaveBeenCalledTimes(1);
    expect(onPalette).not.toHaveBeenCalled();
  });

  it("não chama onHelp para '?' com foco em um input", () => {
    const onPalette = vi.fn();
    const onHelp = vi.fn();
    renderHook(() => useShortcuts({ onPalette, onHelp }));
    const { container } = render(<input aria-label="campo" />);
    const input = container.querySelector("input")!;
    fireEvent.keyDown(input, { key: "?" });
    expect(onHelp).not.toHaveBeenCalled();
  });

  it("previne o comportamento padrão para Ctrl+K", () => {
    const onPalette = vi.fn();
    const onHelp = vi.fn();
    renderHook(() => useShortcuts({ onPalette, onHelp }));
    const event = new KeyboardEvent("keydown", {
      key: "k",
      ctrlKey: true,
      cancelable: true,
      bubbles: true,
    });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });
});
