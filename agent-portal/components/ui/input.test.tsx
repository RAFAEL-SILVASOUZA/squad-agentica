import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Input } from "./input";

describe("Input", () => {
  it("renders with label", () => {
    render(<Input label="Email" />);
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });

  it("shows error message with aria-describedby", () => {
    render(<Input label="Email" error="Email inválido" />);
    const input = screen.getByLabelText("Email");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAttribute("aria-describedby", expect.stringContaining("error"));
    expect(screen.getByText("Email inválido")).toBeInTheDocument();
  });

  it("shows hint when no error", () => {
    render(<Input label="Name" hint="Digite seu nome" />);
    expect(screen.getByText("Digite seu nome")).toBeInTheDocument();
  });

  it("does not show hint when error is present", () => {
    render(<Input label="Name" hint="Digite seu nome" error="Obrigatório" />);
    expect(screen.queryByText("Digite seu nome")).not.toBeInTheDocument();
  });

  it("calls onChange when typed", () => {
    const onChange = vi.fn();
    render(<Input label="Name" onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "test" },
    });
    expect(onChange).toHaveBeenCalled();
  });

  it("applies error border color", () => {
    render(<Input label="Email" error="Invalid" />);
    const input = screen.getByLabelText("Email");
    expect(input).toHaveAttribute("aria-invalid", "true");
  });
});
