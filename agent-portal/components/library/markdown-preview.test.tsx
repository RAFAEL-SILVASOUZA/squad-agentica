import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MarkdownPreview, renderMarkdown } from "./markdown-preview";

describe("renderMarkdown", () => {
  it("renders headings with level", () => {
    const html = renderMarkdown("# Título\n## Subtítulo");
    expect(html).toContain("<h1");
    expect(html).toContain("Título");
    expect(html).toContain("<h2");
    expect(html).toContain("Subtítulo");
  });

  it("renders paragraphs", () => {
    const html = renderMarkdown("Olá mundo");
    expect(html).toContain("<p");
    expect(html).toContain("Olá mundo");
  });

  it("renders bullet lists", () => {
    const html = renderMarkdown("- item um\n- item dois");
    expect(html).toContain("<ul");
    expect(html).toContain("<li>item um</li>");
    expect(html).toContain("<li>item dois</li>");
  });

  it("renders inline code", () => {
    const html = renderMarkdown("use `npm run dev` para rodar");
    expect(html).toContain("<code");
    expect(html).toContain("npm run dev");
  });

  it("renders fenced code blocks", () => {
    const html = renderMarkdown("```\nconst x = 1;\n```");
    expect(html).toContain("<pre");
    expect(html).toContain("const x = 1;");
  });

  it("renders bold and italic", () => {
    const html = renderMarkdown("**forte** e *itálico*");
    expect(html).toContain("<strong>forte</strong>");
    expect(html).toContain("<em>itálico</em>");
  });

  it("escapes HTML in source", () => {
    const html = renderMarkdown("<script>alert(1)</script>");
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
  });
});

describe("MarkdownPreview", () => {
  it("shows placeholder when source is empty", () => {
    render(<MarkdownPreview source="" />);
    expect(screen.getByText(/nada para pré-visualizar/i)).toBeInTheDocument();
  });

  it("renders markdown content", () => {
    const { container } = render(<MarkdownPreview source="# Olá\n\nTexto **negrito**" />);
    expect(container.querySelector("h1")?.textContent).toContain("Olá");
    expect(container.querySelector("strong")?.textContent).toBe("negrito");
  });
});
