"use client";

import * as React from "react";

/**
 * MarkdownPreview (fe-library, local).
 * Renderizador markdown mínimo (sem dependência externa: package.json é de
 * outro dono e não há lib de markdown instalada).
 * Suporta: headings (#..######), parágrafos, listas (- / *), código inline
 * (`...`), blocos de código (```), negrito (**...**) e itálico (*...*).
 * Saída é HTML sanitizado (escapado) e injetado via dangerouslySetInnerHTML.
 */

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function inline(text: string): string {
  let out = escapeHtml(text);
  out = out.replace(/`([^`]+)`/g, '<code style="font-family:var(--font-mono);font-size:12px;background:var(--bg-hover);padding:1px 4px;border-radius:3px;">$1</code>');
  out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  out = out.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
  return out;
}

export function renderMarkdown(source: string): string {
  const lines = source.split(/\r?\n/);
  const html: string[] = [];
  let inCode = false;
  let codeLines: string[] = [];
  let listItems: string[] = [];
  let paragraph: string[] = [];

  const flushParagraph = () => {
    if (paragraph.length > 0) {
      html.push(`<p style="margin:0 0 8px;font-size:13px;line-height:1.6;">${inline(paragraph.join(" "))}</p>`);
      paragraph = [];
    }
  };

  const flushList = () => {
    if (listItems.length > 0) {
      html.push(
        `<ul style="margin:0 0 8px;padding-left:20px;font-size:13px;line-height:1.7;">${listItems
          .map((item) => `<li>${inline(item)}</li>`)
          .join("")}</ul>`
      );
      listItems = [];
    }
  };

  for (const rawLine of lines) {
    const line = rawLine;

    if (line.trim().startsWith("```")) {
      if (inCode) {
        html.push(
          `<pre style="background:var(--bg-elevated);border:1px solid var(--border);border-radius:var(--radius-sm);padding:12px;overflow-x:auto;font-family:var(--font-mono);font-size:12px;line-height:1.5;margin:0 0 8px;">${escapeHtml(codeLines.join("\n"))}</pre>`
        );
        codeLines = [];
        inCode = false;
      } else {
        flushParagraph();
        flushList();
        inCode = true;
      }
      continue;
    }

    if (inCode) {
      codeLines.push(line);
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      flushParagraph();
      flushList();
      const level = heading[1].length;
      const sizes = ["18px", "16px", "14px", "13px", "12px", "12px"];
      html.push(
        `<h${level} style="font-size:${sizes[level - 1]};font-weight:600;color:var(--text);margin:12px 0 6px;">${inline(heading[2])}</h${level}>`
      );
      continue;
    }

    const listItem = line.match(/^\s*[-*]\s+(.*)$/);
    if (listItem) {
      flushParagraph();
      listItems.push(listItem[1]);
      continue;
    }

    if (line.trim() === "") {
      flushParagraph();
      flushList();
      continue;
    }

    flushList();
    paragraph.push(line.trim());
  }

  if (inCode && codeLines.length > 0) {
    html.push(
      `<pre style="background:var(--bg-elevated);border:1px solid var(--border);border-radius:var(--radius-sm);padding:12px;overflow-x:auto;font-family:var(--font-mono);font-size:12px;line-height:1.5;margin:0 0 8px;">${escapeHtml(codeLines.join("\n"))}</pre>`
    );
  }
  flushParagraph();
  flushList();

  return html.join("");
}

export interface MarkdownPreviewProps {
  source: string;
  style?: React.CSSProperties;
}

export function MarkdownPreview({ source, style }: MarkdownPreviewProps) {
  const html = React.useMemo(() => renderMarkdown(source), [source]);

  if (!source.trim()) {
    return (
      <div
        style={{
          fontSize: "12px",
          color: "var(--text-muted)",
          fontStyle: "italic",
          ...style,
        }}
      >
        Nada para pré-visualizar ainda.
      </div>
    );
  }

  return (
    <div
      aria-label="Pré-visualização markdown"
      style={{
        fontSize: "13px",
        color: "var(--text)",
        overflowWrap: "break-word",
        ...style,
      }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
