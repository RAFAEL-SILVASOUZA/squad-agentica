"use client";

import * as React from "react";

export interface UseShortcutsOptions {
  onPalette: () => void;
  onHelp: () => void;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || target.isContentEditable;
}

/**
 * Atalhos de teclado globais: Ctrl/⌘+K abre a paleta (sempre),
 * "/" abre a paleta e "?" abre a ajuda (fora de campos editáveis).
 */
export function useShortcuts({ onPalette, onHelp }: UseShortcutsOptions) {
  const onPaletteRef = React.useRef(onPalette);
  const onHelpRef = React.useRef(onHelp);

  React.useEffect(() => {
    onPaletteRef.current = onPalette;
  }, [onPalette]);

  React.useEffect(() => {
    onHelpRef.current = onHelp;
  }, [onHelp]);

  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        onPaletteRef.current();
        return;
      }

      if (e.key === "/" || e.key === "?") {
        if (isEditableTarget(e.target)) return;
        e.preventDefault();
        if (e.key === "/") onPaletteRef.current();
        else onHelpRef.current();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);
}
