import { render } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Skeleton } from "./skeleton";

describe("Skeleton", () => {
  it("renders with default dimensions", () => {
    const { container } = render(<Skeleton />);
    const el = container.firstElementChild;
    expect(el).toBeInTheDocument();
    expect(el).toHaveStyle({ width: "100%", height: "16px" });
  });

  it("renders with custom dimensions", () => {
    const { container } = render(<Skeleton width={200} height={40} />);
    const el = container.firstElementChild;
    expect(el).toHaveStyle({ width: "200px", height: "40px" });
  });

  it("has shimmer animation", () => {
    const { container } = render(<Skeleton />);
    const el = container.firstElementChild;
    expect(el).toHaveStyle({ animation: "shimmer 1.5s ease-in-out infinite" });
  });

  it("is aria-hidden", () => {
    const { container } = render(<Skeleton />);
    const el = container.firstElementChild;
    expect(el).toHaveAttribute("aria-hidden", "true");
  });

  it("applies custom border radius", () => {
    const { container } = render(<Skeleton borderRadius={12} />);
    const el = container.firstElementChild;
    expect(el).toHaveStyle({ borderRadius: "12px" });
  });
});
