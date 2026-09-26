import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import LoginPage from "./page";

// Use vi.hoisted to define mocks before vi.mock (which is hoisted)
const { mockSignIn, mockUseSession, mockRouter, mockSearchParams } = vi.hoisted(() => {
  const mockSignIn = vi.fn();
  const mockUseSession = vi.fn();
  const mockRouter = { push: vi.fn(), replace: vi.fn(), refresh: vi.fn() };
  const mockSearchParams = new URLSearchParams();
  return { mockSignIn, mockUseSession, mockRouter, mockSearchParams };
});

vi.mock("next-auth/react", () => ({
  signIn: (...args: unknown[]) => mockSignIn(...args),
  useSession: () => mockUseSession(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => mockRouter,
  useSearchParams: () => mockSearchParams,
}));

describe("LoginPage", () => {
  beforeEach(() => {
    // Reset call history but keep implementations
    mockSignIn.mockClear();
    mockUseSession.mockClear();
    mockRouter.push.mockClear();
    mockRouter.replace.mockClear();
    mockRouter.refresh.mockClear();
    mockUseSession.mockReturnValue({ data: null, status: "unauthenticated" });
    mockSearchParams.set("callbackUrl", "/");
  });

  it("renders email and password fields with labels", () => {
    render(<LoginPage />);
    expect(screen.getByLabelText(/e-mail/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/senha/i)).toBeInTheDocument();
  });

  it("shows validation error for empty email", async () => {
    render(<LoginPage />);
    const submitBtn = screen.getByRole("button", { name: /entrar/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText("Email é obrigatório")).toBeInTheDocument();
    });
  });

  it("shows validation error for invalid email format", async () => {
    render(<LoginPage />);
    const emailInput = screen.getByLabelText(/e-mail/i);
    fireEvent.change(emailInput, { target: { value: "not-an-email" } });

    const submitBtn = screen.getByRole("button", { name: /entrar/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText("Email inválido")).toBeInTheDocument();
    });
  });

  it("shows validation error for short password", async () => {
    render(<LoginPage />);
    const emailInput = screen.getByLabelText(/e-mail/i);
    const passwordInput = screen.getByLabelText(/senha/i);
    fireEvent.change(emailInput, { target: { value: "test@test.com" } });
    fireEvent.change(passwordInput, { target: { value: "short" } });

    const submitBtn = screen.getByRole("button", { name: /entrar/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(
        screen.getByText("Senha deve ter no mínimo 8 caracteres")
      ).toBeInTheDocument();
    });
  });

  it("submits form with valid credentials without validation errors", async () => {
    mockSignIn.mockResolvedValue({ error: null });
    const user = userEvent.setup();
    render(<LoginPage />);

    const emailInput = screen.getByLabelText(/e-mail/i);
    const passwordInput = screen.getByLabelText(/senha/i);
    await user.type(emailInput, "admin@local.com");
    await user.type(passwordInput, "password123");

    const submitBtn = screen.getByRole("button", { name: /entrar/i });
    await user.click(submitBtn);

    // No validation errors should be shown
    await waitFor(() => {
      expect(screen.queryByText("Email é obrigatório")).not.toBeInTheDocument();
      expect(screen.queryByText("Email inválido")).not.toBeInTheDocument();
      expect(screen.queryByText("Senha é obrigatória")).not.toBeInTheDocument();
      expect(screen.queryByText("Senha deve ter no mínimo 8 caracteres")).not.toBeInTheDocument();
    });
  });

  it("shows loading state during submission", async () => {
    let resolveSignIn: (v: { error: null }) => void;
    mockSignIn.mockReturnValue(
      new Promise((resolve) => {
        resolveSignIn = resolve;
      })
    );
    const user = userEvent.setup();
    render(<LoginPage />);

    const emailInput = screen.getByLabelText(/e-mail/i);
    const passwordInput = screen.getByLabelText(/senha/i);
    await user.type(emailInput, "admin@local.com");
    await user.type(passwordInput, "password123");

    const submitBtn = screen.getByRole("button", { name: /entrar/i });
    await user.click(submitBtn);

    // Button should show loading state
    await waitFor(
      () => {
        expect(screen.getByRole("button")).toHaveTextContent(/entrando/i);
      },
      { timeout: 2000 }
    );

    // Resolve to unblock
    resolveSignIn!({ error: null });
  });

  it("shows link to register page", () => {
    render(<LoginPage />);
    const link = screen.getByText(/criar conta/i);
    expect(link).toHaveAttribute("href", "/register");
  });

  it("shows error banner from URL params", () => {
    mockSearchParams.set("error", "CredentialsSignin");
    render(<LoginPage />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("redirects if already authenticated", async () => {
    mockUseSession.mockReturnValue({
      data: { user: { id: "1", email: "a@b.com", name: "A" } },
      status: "authenticated",
    });
    render(<LoginPage />);

    await waitFor(() => {
      expect(mockRouter.replace).toHaveBeenCalledWith("/");
    });
  });
});
