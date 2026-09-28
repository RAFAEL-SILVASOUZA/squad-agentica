"use client";

import * as React from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Markdown (design system): renderiza a saída dos agentes (títulos, listas,
 * tabelas GFM, código). Genérico — também usado pelo chat do Knowledge.
 *
 * Segurança: sem `rehype-raw`, HTML cru no texto vira texto (nada de
 * <script>); links abrem em nova aba com `rel="noreferrer"`. A tipografia
 * fica na classe `.markdown` de `app/globals.css`.
 */
export interface MarkdownProps {
  children: string;
  className?: string;
}

const components: Components = {
  a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noreferrer" />,
};

export function Markdown({ children, className }: MarkdownProps) {
  return (
    <div className={className ? `markdown ${className}` : "markdown"}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
