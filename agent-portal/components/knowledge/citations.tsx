"use client";

import * as React from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatSource } from "./types";

/**
 * Citations: renderiza markdown e substitui [n] por <sup><button>n</button></sup>.
 * Fora de blocos de código. O botão abre a fonte via onOpen(index).
 */
export interface CitationsProps {
  text: string;
  sources: ChatSource[];
  onOpen: (index: number) => void;
}

const CIT_START = "\u0001";
const CIT_END = "\u0002";

/**
 * Substitui [n] (fora de blocos de código) por um marcador único que o
 * componente de texto do ReactMarkdown converte em botão de citação.
 */
function markCitations(text: string, sources: ChatSource[]): string {
  const parts = text.split(/(```[\s\S]*?```)/g);
  return parts
    .map((part, i) => {
      if (i % 2 === 1) return part; // bloco de código
      const inlineParts = part.split(/(`[^`]*`)/g);
      return inlineParts
        .map((seg, j) => {
          if (j % 2 === 1) return seg; // inline code
          return seg.replace(/\[(\d+)\]/g, (_, num) => {
            const idx = parseInt(num, 10) - 1;
            if (idx >= 0 && idx < sources.length) {
              return `${CIT_START}CIT${idx}${CIT_END}`;
            }
            return `[${num}]`;
          });
        })
        .join("");
    })
    .join("");
}

function renderCitationText(
  text: string,
  onOpen: (index: number) => void
): React.ReactNode {
  const parts = text.split(new RegExp(`(${CIT_START}CIT(\\d+)${CIT_END})`, "g"));
  if (parts.length === 1) return text;
  return parts.map((part, i) => {
    const match = part.match(new RegExp(`^${CIT_START}CIT(\\d+)${CIT_END}$`));
    if (match) {
      const idx = parseInt(match[1], 10);
      return (
        <sup key={i} style={{ margin: "0 1px" }}>
          <button
            type="button"
            aria-label={`Fonte ${idx + 1}`}
            onClick={() => onOpen(idx)}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              color: "var(--accent)",
              fontSize: "10px",
              fontWeight: 600,
              padding: "0 2px",
              verticalAlign: "super",
            }}
          >
            {idx + 1}
          </button>
        </sup>
      );
    }
    return <React.Fragment key={i}>{part}</React.Fragment>;
  });
}

function containsCitation(node: React.ReactNode): boolean {
  if (typeof node === "string") return node.includes(CIT_START);
  if (Array.isArray(node)) return node.some(containsCitation);
  if (React.isValidElement(node)) {
    const el = node as React.ReactElement<{ children?: React.ReactNode }>;
    return el.props.children ? containsCitation(el.props.children) : false;
  }
  return false;
}

function transformChildren(
  children: React.ReactNode,
  onOpen: (index: number) => void
): React.ReactNode {
  if (!containsCitation(children)) return children;
  if (typeof children === "string") {
    return renderCitationText(children, onOpen);
  }
  if (Array.isArray(children)) {
    return children.map((child, i) => (
      <React.Fragment key={i}>{transformChildren(child, onOpen)}</React.Fragment>
    ));
  }
  if (React.isValidElement(children)) {
    const el = children as React.ReactElement<{ children?: React.ReactNode }>;
    if (el.props.children) {
      return React.cloneElement(el, {
        children: transformChildren(el.props.children, onOpen),
      });
    }
  }
  return children;
}

export function Citations({ text, sources, onOpen }: CitationsProps) {
  const marked = React.useMemo(() => markCitations(text, sources), [text, sources]);
  const hasCitations = marked.includes(CIT_START);

  const components: Components = React.useMemo(() => {
    const base: Components = {
      a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noreferrer" />,
    };
    if (!hasCitations) return base;
    base.p = ({ node: _node, children, ...props }) => (
      <p {...props}>{transformChildren(children, onOpen)}</p>
    );
    base.li = ({ node: _node, children, ...props }) => (
      <li {...props}>{transformChildren(children, onOpen)}</li>
    );
    base.strong = ({ node: _node, children, ...props }) => (
      <strong {...props}>{transformChildren(children, onOpen)}</strong>
    );
    base.em = ({ node: _node, children, ...props }) => (
      <em {...props}>{transformChildren(children, onOpen)}</em>
    );
    return base;
  }, [hasCitations, onOpen]);

  return (
    <div className="markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {marked}
      </ReactMarkdown>
    </div>
  );
}
