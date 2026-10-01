"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import { MoreVertical } from "lucide-react";

/**
 * Popover (adendo 7.1): menu flutuante renderizado num portal no `body`, com
 * `position: fixed` calculado pelo botão que o abriu. Nunca fica dentro de um
 * container com overflow (resolve o menu ⋮ cortado do DataTable).
 *
 * - Abre para cima quando falta espaço embaixo.
 * - Reposiciona ao rolar ou redimensionar; fecha se não couber.
 * - Fecha com ESC e ao clicar fora; devolve o foco ao botão.
 */
export interface PopoverProps {
  open: boolean;
  onClose: () => void;
  /** Botão (ou elemento) que abriu o popover: a posição é calculada dele. */
  anchorRef: React.RefObject<HTMLElement | null>;
  children: React.ReactNode;
  /** Alinhamento horizontal em relação ao âncora. */
  align?: "start" | "end";
  /** Largura mínima do painel (px). */
  minWidth?: number;
}

const GAP = 4;
const MARGIN = 8;

interface PopoverPosition {
  top: number;
  left: number;
  visible: boolean;
}

/**
 * Calcula a posição `fixed` do painel a partir do retângulo do âncora e da
 * altura real do painel. Abre para cima quando falta espaço embaixo.
 */
function computePosition(
  anchor: HTMLElement,
  panelHeight: number,
  align: "start" | "end",
  minWidth: number
): PopoverPosition {
  const rect = anchor.getBoundingClientRect();
  const viewportH = window.innerHeight;
  const viewportW = window.innerWidth;

  const width = Math.max(minWidth, rect.width);
  const spaceBelow = viewportH - rect.bottom;
  const openUpward = spaceBelow < panelHeight + GAP;

  let left = align === "end" ? rect.right - width : rect.left;
  left = Math.max(MARGIN, Math.min(left, viewportW - width - MARGIN));

  let top: number;
  if (openUpward) {
    top = rect.top - panelHeight - GAP;
    if (top < MARGIN) top = MARGIN;
  } else {
    top = rect.bottom + GAP;
    if (top + panelHeight > viewportH - MARGIN) {
      top = Math.max(MARGIN, viewportH - panelHeight - MARGIN);
    }
  }

  return { top, left, visible: true };
}

export function Popover({
  open,
  onClose,
  anchorRef,
  children,
  align = "end",
  minWidth = 140,
}: PopoverProps) {
  const panelRef = React.useRef<HTMLDivElement>(null);
  const [position, setPosition] = React.useState<PopoverPosition | null>(null);
  const [measured, setMeasured] = React.useState(false);

  const onCloseRef = React.useRef(onClose);
  onCloseRef.current = onClose;

  // Calcula a posição ao abrir e ao rolar/redimensionar. A altura real do
  // painel é medida após o primeiro render (dois passes: render invisível,
  // medir, render na posição final).
  React.useEffect(() => {
    if (!open) {
      setPosition(null);
      setMeasured(false);
      return;
    }

    // Copia o âncora para uma variável local: o cleanup usa essa referência
    // (o valor de `anchorRef.current` pode mudar até o cleanup rodar).
    const anchorEl = anchorRef.current;

    const update = () => {
      if (!anchorEl) return;
      const panelHeight = panelRef.current?.offsetHeight ?? 0;
      setPosition(computePosition(anchorEl, panelHeight, align, minWidth));
    };

    update();
    // Medição da altura real (após o primeiro paint).
    const raf = requestAnimationFrame(() => {
      setMeasured(true);
      update();
    });

    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
      // Devolve o foco ao âncora ao fechar.
      anchorEl?.focus?.();
    };
  }, [open, anchorRef, align, minWidth]);

  // ESC fecha e clique fora fecha.
  React.useEffect(() => {
    if (!open) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCloseRef.current();
    };
    const handlePointerDown = (e: MouseEvent) => {
      const target = e.target as Node;
      const panel = panelRef.current;
      const anchor = anchorRef.current;
      if (panel && panel.contains(target)) return;
      if (anchor && anchor.contains(target)) return;
      onCloseRef.current();
    };

    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("mousedown", handlePointerDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, [open, anchorRef]);

  if (!open || !position) return null;

  return createPortal(
    <div
      ref={panelRef}
      role="menu"
      style={{
        position: "fixed",
        top: position.top,
        left: position.left,
        minWidth,
        background: "var(--bg-elevated)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-sm)",
        boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
        zIndex: 10000,
        padding: "4px 0",
        visibility: measured ? "visible" : "hidden",
      }}
    >
      {children}
    </div>,
    document.body
  );
}

/**
 * RowMenu (adendo 7.1): conveniência para o menu ⋮ de linha. Encapsula o
 * botão de gatilho (MoreVertical) + Popover + itens. Um único componente, sem
 * cópias, usado no desktop e no mobile do DataTable.
 */
export interface RowMenuItem {
  label: string;
  action: string;
  danger?: boolean;
}

export interface RowMenuProps {
  items: RowMenuItem[];
  onAction: (action: string) => void;
  /** Rótulo acessível do botão. */
  label?: string;
  /** Tamanho do ícone (px). */
  iconSize?: number;
  /** Alinhamento do popover em relação ao botão. */
  align?: "start" | "end";
}

export function RowMenu({
  items,
  onAction,
  label = "Ações",
  iconSize = 14,
  align = "end",
}: RowMenuProps) {
  const [open, setOpen] = React.useState(false);
  const anchorRef = React.useRef<HTMLButtonElement>(null);

  const handleAction = (action: string) => {
    setOpen(false);
    onAction(action);
  };

  return (
    <>
      <button
        ref={anchorRef}
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        style={{
          background: "none",
          border: "none",
          cursor: "pointer",
          color: "var(--text-muted)",
          padding: "4px",
          display: "flex",
          alignItems: "center",
        }}
      >
        <MoreVertical size={iconSize} aria-hidden="true" />
      </button>
      <Popover open={open} onClose={() => setOpen(false)} anchorRef={anchorRef} align={align}>
        {items.map((item) => (
          <button
            key={item.action}
            type="button"
            role="menuitem"
            onClick={(e) => {
              e.stopPropagation();
              handleAction(item.action);
            }}
            style={{
              display: "block",
              width: "100%",
              padding: "8px 12px",
              fontSize: "12px",
              textAlign: "left",
              background: "none",
              border: "none",
              cursor: "pointer",
              color: item.danger ? "var(--error)" : "var(--text)",
              whiteSpace: "nowrap",
            }}
          >
            {item.label}
          </button>
        ))}
      </Popover>
    </>
  );
}
