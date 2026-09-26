import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Select } from "./select";

const options = [
  { value: "a", label: "Option A" },
  { value: "b", label: "Option B" },
  { value: "c", label: "Option C", disabled: true },
];

describe("Select", () => {
  it("renders with label and options", () => {
    render(<Select label="Choose" options={options} />);
    expect(screen.getByLabelText("Choose")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Option A" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Option B" })).toBeInTheDocument();
  });

  it("renders placeholder when provided", () => {
    render(<Select label="Choose" options={options} placeholder="Select..." />);
    expect(screen.getByRole("option", { name: "Select..." })).toBeInTheDocument();
  });

  it("calls onValueChange when selection changes", () => {
    const onValueChange = vi.fn();
    render(<Select label="Choose" options={options} onValueChange={onValueChange} />);
    fireEvent.change(screen.getByLabelText("Choose"), {
      target: { value: "b" },
    });
    expect(onValueChange).toHaveBeenCalledWith("b");
  });

  it("shows error message", () => {
    render(<Select label="Choose" options={options} error="Required" />);
    expect(screen.getByText("Required")).toBeInTheDocument();
    expect(screen.getByLabelText("Choose")).toHaveAttribute("aria-invalid", "true");
  });

  it("disables disabled options", () => {
    render(<Select label="Choose" options={options} />);
    expect(screen.getByRole("option", { name: "Option C" })).toBeDisabled();
  });
});
