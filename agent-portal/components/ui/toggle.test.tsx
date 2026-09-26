import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Toggle } from "./toggle";

describe("Toggle", () => {
  it("renders with label", () => {
    render(<Toggle checked={false} onChange={() => {}} label="Enable feature" />);
    expect(screen.getByText("Enable feature")).toBeInTheDocument();
  });

  it("shows correct aria-checked state", () => {
    render(<Toggle checked={true} onChange={() => {}} label="Feature" />);
    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "true");
  });

  it("calls onChange with inverted value", () => {
    const onChange = vi.fn();
    render(<Toggle checked={false} onChange={onChange} label="Feature" />);
    fireEvent.click(screen.getByRole("switch"));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("does not call onChange when disabled", () => {
    const onChange = vi.fn();
    render(
      <Toggle checked={false} onChange={onChange} label="Feature" disabled />
    );
    const toggle = screen.getByRole("switch");
    expect(toggle).toBeDisabled();
    fireEvent.click(toggle);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("shows description when provided", () => {
    render(
      <Toggle
        checked={false}
        onChange={() => {}}
        label="Feature"
        description="Enables the feature"
      />
    );
    expect(screen.getByText("Enables the feature")).toBeInTheDocument();
  });
});
