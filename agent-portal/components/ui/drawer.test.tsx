import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Drawer } from "./drawer";

describe("Drawer", () => {
  it("renders when open", () => {
    render(
      <Drawer open onClose={() => {}} title="Test Drawer">
        <p>Drawer content</p>
      </Drawer>
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Drawer content")).toBeInTheDocument();
  });

  it("does not render when closed", () => {
    render(
      <Drawer open={false} onClose={() => {}} title="Test Drawer">
        <p>Content</p>
      </Drawer>
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("calls onClose when ESC is pressed", () => {
    const onClose = vi.fn();
    render(
      <Drawer open onClose={onClose} title="Test Drawer">
        <p>Content</p>
      </Drawer>
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("calls onClose when clicking overlay", () => {
    const onClose = vi.fn();
    render(
      <Drawer open onClose={onClose} title="Test Drawer">
        <p>Content</p>
      </Drawer>
    );
    const overlay = screen.getByRole("dialog");
    fireEvent.click(overlay);
    expect(onClose).toHaveBeenCalled();
  });

  it("applies custom width", () => {
    render(
      <Drawer open onClose={() => {}} title="Test" width={400}>
        <p>Content</p>
      </Drawer>
    );
    const panel = screen.getByRole("dialog").firstElementChild;
    expect(panel).toHaveStyle({ width: "400px" });
  });
});
