import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import ForgotPasswordPage from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

describe("ForgotPasswordPage", () => {
  it("explains that the admin must reset the password", () => {
    render(<ForgotPasswordPage />);
    expect(
      screen.getByText("Peça ao administrador…", { exact: false })
    ).toBeInTheDocument();
  });

  it("has a 'Voltar para o login' link pointing to /login", () => {
    render(<ForgotPasswordPage />);
    const link = screen.getByText("Voltar para o login");
    expect(link).toHaveAttribute("href", "/login");
  });
});
