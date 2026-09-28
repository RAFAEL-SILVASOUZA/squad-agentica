import * as React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Markdown } from "./markdown";

describe("Markdown", () => {
  it("renders headings, lists and code; keeps raw HTML as text", () => {
    const { container } = render(
      <Markdown>{"# Título\n\n- item\n\n`code`\n\n<script>alert(1)</script>"}</Markdown>
    );
    expect(container.querySelector("h1")?.textContent).toBe("Título");
    expect(container.querySelector("li")?.textContent).toBe("item");
    expect(container.querySelector("code")?.textContent).toBe("code");
    expect(container.querySelector("script")).toBeNull();
  });

  it("renders GFM tables and opens links in a new tab without referrer", () => {
    const { container } = render(
      <Markdown className="extra">{"| a | b |\n|---|---|\n| 1 | 2 |\n\n[site](https://example.com)"}</Markdown>
    );
    expect(container.querySelector("table")).not.toBeNull();
    expect(container.firstElementChild).toHaveClass("markdown", "extra");
    const link = screen.getByRole("link", { name: "site" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
  });
});
