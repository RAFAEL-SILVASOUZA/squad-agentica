import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Modal } from "./modal";

describe("Modal", () => {
  it("renders when open", () => {
    render(
      <Modal open onClose={() => {}} title="Test Modal">
        <p>Modal content</p>
      </Modal>
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Modal content")).toBeInTheDocument();
  });

  it("does not render when closed", () => {
    render(
      <Modal open={false} onClose={() => {}} title="Test Modal">
        <p>Modal content</p>
      </Modal>
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("calls onClose when ESC is pressed", () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="Test Modal">
        <p>Content</p>
      </Modal>
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("calls onClose when clicking overlay", () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="Test Modal">
        <p>Content</p>
      </Modal>
    );
    const overlay = screen.getByRole("dialog");
    fireEvent.click(overlay);
    expect(onClose).toHaveBeenCalled();
  });

  it("renders footer when provided", () => {
    render(
      <Modal open onClose={() => {}} title="Test" footer={<button>OK</button>}>
        <p>Content</p>
      </Modal>
    );
    expect(screen.getByRole("button", { name: "OK" })).toBeInTheDocument();
  });

  it("has aria-modal attribute", () => {
    render(
      <Modal open onClose={() => {}} title="Test Modal">
        <p>Content</p>
      </Modal>
    );
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-modal", "true");
  });
});
