import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Card } from "./card";

describe("Card", () => {
  it("renders with default variant", () => {
    render(<Card>Content</Card>);
    expect(screen.getByText("Content")).toBeInTheDocument();
  });

  it("renders with stat variant", () => {
    render(<Card variant="stat">Stat</Card>);
    const card = screen.getByText("Stat").closest("div");
    expect(card).toHaveStyle({ padding: "12px 14px" });
  });

  it("applies hover styles when hoverable", () => {
    const onMouseEnter = vi.fn();
    render(
      <Card hoverable onMouseEnter={onMouseEnter}>
        Hover
      </Card>
    );
    const card = screen.getByText("Hover").closest("div");
    fireEvent.mouseEnter(card!);
    expect(onMouseEnter).toHaveBeenCalled();
  });

  it("does not apply hover cursor when not hoverable", () => {
    render(<Card>Static</Card>);
    const card = screen.getByText("Static").closest("div");
    expect(card).not.toHaveStyle({ cursor: "pointer" });
  });

  it("applies custom className", () => {
    render(<Card className="custom-class">Content</Card>);
    expect(screen.getByText("Content").closest("div")).toHaveClass("custom-class");
  });
});
