import * as React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

  it("size xl widens the panel (grafo do monitor)", () => {
    render(
      <Modal open onClose={() => {}} title="Grafo" size="xl">
        <p>grafo</p>
      </Modal>
    );
    const panel = screen.getByText("grafo").closest("[tabindex='-1']") as HTMLElement;
    expect(panel.style.maxWidth).toBe("min(1200px, 95vw)");
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

  it("keeps focus in the field while the parent re-renders on each keystroke", async () => {
    function Form() {
      const [value, setValue] = React.useState("");
      return (
        <Modal open onClose={() => {}} title="Form">
          <label htmlFor="f">Nome</label>
          <input id="f" value={value} onChange={(e) => setValue(e.target.value)} />
        </Modal>
      );
    }
    render(<Form />);
    const input = screen.getByLabelText("Nome");
    await userEvent.click(input);
    await userEvent.keyboard("revisar-especificacao");
    expect(input).toHaveValue("revisar-especificacao");
    expect(input).toHaveFocus();
  });
});
