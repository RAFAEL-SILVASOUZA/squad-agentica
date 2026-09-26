import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Button } from "./button";

describe("Button", () => {
  it("renders with default variant", () => {
    render(<Button>Click me</Button>);
    const btn = screen.getByRole("button", { name: "Click me" });
    expect(btn).toBeInTheDocument();
    expect(btn).toHaveStyle({ background: "var(--bg-card)" });
  });

  it("renders with primary variant", () => {
    render(<Button variant="primary">Primary</Button>);
    const btn = screen.getByRole("button", { name: "Primary" });
    expect(btn).toHaveStyle({ background: "var(--accent)" });
  });

  it("renders with sm size", () => {
    render(<Button size="sm">Small</Button>);
    const btn = screen.getByRole("button", { name: "Small" });
    expect(btn).toHaveStyle({ padding: "6px 12px" });
  });

  it("calls onClick when clicked", () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Click</Button>);
    fireEvent.click(screen.getByRole("button", { name: "Click" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("does not call onClick when disabled", () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        Disabled
      </Button>
    );
    const btn = screen.getByRole("button", { name: "Disabled" });
    expect(btn).toBeDisabled();
    fireEvent.click(btn);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("shows spinner when loading", () => {
    render(<Button loading>Loading</Button>);
    const btn = screen.getByRole("button", { name: /loading/i });
    expect(btn).toBeDisabled();
    expect(btn.querySelector('[aria-hidden="true"]')).toBeInTheDocument();
  });

  it("applies aria-disabled when loading", () => {
    render(<Button loading>Loading</Button>);
    const btn = screen.getByRole("button", { name: /loading/i });
    expect(btn).toHaveAttribute("aria-disabled", "true");
  });
});
