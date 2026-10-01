"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

/**
 * Modal (design system §2.10, adendo 7).
 * Overlay + painel centralizado. ESC fecha (exceto durante operação em
 * andamento), clique fora fecha, foco preso no painel e devolvido ao elemento
 * que abriu. Abaixo de 768px vira folha em tela cheia (100dvh) com cabeçalho
 * e rodapé fixos e rolagem só no miolo.
 */
export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  /**
   * Largura do painel (adendo 7.1):
   * sm 440px (confirmações), md 640px (formulários curtos),
   * lg 1040px (formulários ricos), xl 1200px (grafo, aprovações).
   * Sempre min(tamanho, 95vw).
   */
  size?: "sm" | "md" | "lg" | "xl";
  /**
   * Operação em andamento (ex.: salvando). Impede que ESC feche a modal
   * enquanto a requisição roda.
   */
  busy?: boolean;
}

const SIZE_MAX_WIDTH: Record<NonNullable<ModalProps["size"]>, string> = {
  sm: "min(440px, 95vw)",
  md: "min(640px, 95vw)",
  lg: "min(1040px, 95vw)",
  xl: "min(1200px, 95vw)",
};

/** Seletores de elementos focáveis dentro do painel (foco preso). */
const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(", ");

export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  size = "md",
  busy = false,
}: ModalProps) {
  const panelRef = React.useRef<HTMLDivElement>(null);
  const [isMobile, setIsMobile] = React.useState(false);

  // `onClose` costuma ser uma arrow nova a cada render do pai. Com ele nas
  // dependências, o efeito rodava a cada tecla e `panel.focus()` tirava o foco
  // do campo em edição (só o 1º caractere ficava). Foco só ao abrir.
  const onCloseRef = React.useRef(onClose);
  onCloseRef.current = onClose;
  const busyRef = React.useRef(busy);
  busyRef.current = busy;

  // Folha em tela cheia abaixo de 768px (adendo 7.1).
  React.useEffect(() => {
    const mql = window.matchMedia("(max-width: 767px)");
    setIsMobile(mql.matches);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, []);

  React.useEffect(() => {
    if (!open) return;

    // Elemento que abriu a modal: o foco volta para ele ao fechar.
    const previouslyFocused = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        // ESC não fecha durante uma operação em andamento (adendo 7.1).
        if (busyRef.current) return;
        onCloseRef.current();
        return;
      }

      // Foco preso: Tab/Shift+Tab circulam dentro do painel.
      if (e.key === "Tab") {
        const panel = panelRef.current;
        if (!panel) return;
        const focusable = Array.from(
          panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
        ).filter((el) => el.offsetParent !== null || el === document.activeElement);

        if (focusable.length === 0) {
          e.preventDefault();
          panel.focus();
          return;
        }

        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        const active = document.activeElement as HTMLElement | null;

        if (e.shiftKey) {
          if (active === first || active === panel || !panel.contains(active)) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (active === last || !panel.contains(active)) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      // Devolve o foco ao elemento que abriu a modal.
      previouslyFocused?.focus?.();
    };
  }, [open]);

  if (!open) return null;

  // Folha em tela cheia (mobile): cabeçalho e rodapé fixos, rolagem só no miolo.
  const panelStyle: React.CSSProperties = isMobile
    ? {
        width: "100%",
        maxWidth: "100%",
        height: "100dvh",
        maxHeight: "100dvh",
        display: "flex",
        flexDirection: "column",
        background: "var(--bg-elevated)",
        border: "none",
        borderRadius: 0,
        boxShadow: "none",
        outline: "none",
      }
    : {
        width: "100%",
        maxWidth: SIZE_MAX_WIDTH[size],
        maxHeight: "min(85vh, 720px)",
        display: "flex",
        flexDirection: "column",
        background: "var(--bg-elevated)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius)",
        boxShadow: "var(--shadow-lg)",
        outline: "none",
      };

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        display: "flex",
        alignItems: isMobile ? "stretch" : "center",
        justifyContent: isMobile ? "stretch" : "center",
        background: "rgba(0,0,0,0.5)",
        animation: "toast-in 0.2s ease",
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div ref={panelRef} tabIndex={-1} style={panelStyle}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "14px 18px",
            borderBottom: "1px solid var(--border)",
            flexShrink: 0,
          }}
        >
          <h2
            style={{
              fontSize: "13px",
              fontWeight: 600,
              color: "var(--text)",
              margin: 0,
            }}
          >
            {title}
          </h2>
          <button
            onClick={onClose}
            aria-label="Fechar"
            style={{
              background: "none",
              border: "none",
              color: "var(--text-muted)",
              cursor: "pointer",
              padding: 4,
              display: "flex",
              alignItems: "center",
              transition: "color var(--transition)",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text)")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-muted)")}
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>
        <div style={{ padding: "18px", overflowY: "auto", flex: "1 1 auto" }}>
          {children}
        </div>
        {footer && (
          <div
            style={{
              padding: "14px 18px",
              borderTop: "1px solid var(--border)",
              display: "flex",
              justifyContent: "flex-end",
              gap: "8px",
              flexShrink: 0,
            }}
          >
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body
  );
}
