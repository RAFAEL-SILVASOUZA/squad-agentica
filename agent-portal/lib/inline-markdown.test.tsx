import { render } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { renderInlineMarkdown } from "./inline-markdown";

describe("renderInlineMarkdown", () => {
  it("renders bold and code without raw markers", () => {
    const { container } = render(
      <p>{renderInlineMarkdown("Adicionei a ação **return** e `finalize`.")}</p>
    );
    expect(container.querySelector("strong")?.textContent).toBe("return");
    expect(container.querySelector("code")?.textContent).toBe("finalize");
    expect(container.textContent).toBe("Adicionei a ação return e finalize.");
  });

  it("keeps markup-looking text literal (no HTML injection)", () => {
    const { container } = render(<p>{renderInlineMarkdown("<b>x</b> 2 * 3")}</p>);
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toBe("<b>x</b> 2 * 3");
  });
});
