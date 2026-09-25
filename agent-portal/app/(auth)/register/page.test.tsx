import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import RegisterPage from "./page";

// Mock next-auth/react
const mockUseSession = vi.fn();

vi.mock("next-auth/react", () => ({
  useSession: () => mockUseSession(),
}));

// Mock next/navigation
const mockRouter = { push: vi.fn(), replace: vi.fn(), refresh: vi.fn() };
const mockSearchParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => mockRouter,
  useSearchParams: () => mockSearchParams,
}));

// Mock auth-client
const mockRegister = vi.fn();
vi.mock("@/lib/auth-client", () => ({
  register: (...args: unknown[]) => mockRegister(...args),
}));

describe("RegisterPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseSession.mockReturnValue({ data: null, status: "unauthenticated" });
    mockSearchParams.set("callbackUrl", "/dashboard");
  });

  it("renders name, email, password and confirm password fields", () => {
    render(<RegisterPage />);
    expect(screen.getByLabelText("Nome")).toBeInTheDocument();
    expect(screen.getByLabelText("E-mail")).toBeInTheDocument();
    expect(screen.getByLabelText("Senha")).toBeInTheDocument();
    expect(screen.getByLabelText("Confirmar senha")).toBeInTheDocument();
  });

  it("shows validation error for empty name", async () => {
    render(<RegisterPage />);
    const submitBtn = screen.getByRole("button", { name: /criar conta/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText("Nome é obrigatório")).toBeInTheDocument();
    });
  });

  it("shows validation error for invalid email", async () => {
    render(<RegisterPage />);
    const emailInput = screen.getByLabelText(/e-mail/i);
    fireEvent.change(emailInput, { target: { value: "invalid" } });

    const submitBtn = screen.getByRole("button", { name: /criar conta/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText("Email inválido")).toBeInTheDocument();
    });
  });

  it("shows validation error for short password", async () => {
    render(<RegisterPage />);
    const emailInput = screen.getByLabelText("E-mail");
    const passwordInput = screen.getByLabelText("Senha");
    fireEvent.change(emailInput, { target: { value: "test@test.com" } });
    fireEvent.change(passwordInput, { target: { value: "123" } });

    const submitBtn = screen.getByRole("button", { name: /criar conta/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(
        screen.getByText("Senha deve ter no mínimo 8 caracteres")
      ).toBeInTheDocument();
    });
  });

  it("shows validation error when passwords don't match", async () => {
    render(<RegisterPage />);
    const emailInput = screen.getByLabelText("E-mail");
    const passwordInput = screen.getByLabelText("Senha");
    const confirmInput = screen.getByLabelText("Confirmar senha");
    fireEvent.change(emailInput, { target: { value: "test@test.com" } });
    fireEvent.change(passwordInput, { target: { value: "password123" } });
    fireEvent.change(confirmInput, { target: { value: "different123" } });

    const submitBtn = screen.getByRole("button", { name: /criar conta/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText("As senhas não coincidem")).toBeInTheDocument();
    });
  });

  it("calls register with valid data", async () => {
    mockRegister.mockResolvedValue({ ok: true });
    render(<RegisterPage />);

    const nameInput = screen.getByLabelText("Nome");
    const emailInput = screen.getByLabelText("E-mail");
    const passwordInput = screen.getByLabelText("Senha");
    const confirmInput = screen.getByLabelText("Confirmar senha");
    fireEvent.change(nameInput, { target: { value: "Test User" } });
    fireEvent.change(emailInput, { target: { value: "test@test.com" } });
    fireEvent.change(passwordInput, { target: { value: "password123" } });
    fireEvent.change(confirmInput, { target: { value: "password123" } });

    const submitBtn = screen.getByRole("button", { name: /criar conta/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockRegister).toHaveBeenCalledWith({
        email: "test@test.com",
        password: "password123",
        name: "Test User",
      });
    });
  });

  it("shows API error on registration failure", async () => {
    mockRegister.mockResolvedValue({
      ok: false,
      error: "email_already_exists",
    });
    render(<RegisterPage />);

    const nameInput = screen.getByLabelText("Nome");
    const emailInput = screen.getByLabelText("E-mail");
    const passwordInput = screen.getByLabelText("Senha");
    const confirmInput = screen.getByLabelText("Confirmar senha");
    fireEvent.change(nameInput, { target: { value: "Test" } });
    fireEvent.change(emailInput, { target: { value: "test@test.com" } });
    fireEvent.change(passwordInput, { target: { value: "password123" } });
    fireEvent.change(confirmInput, { target: { value: "password123" } });

    const submitBtn = screen.getByRole("button", { name: /criar conta/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "email_already_exists"
      );
    });
  });

  it("redirects to callbackUrl on success", async () => {
    mockRegister.mockResolvedValue({ ok: true });
    render(<RegisterPage />);

    const nameInput = screen.getByLabelText("Nome");
    const emailInput = screen.getByLabelText("E-mail");
    const passwordInput = screen.getByLabelText("Senha");
    const confirmInput = screen.getByLabelText("Confirmar senha");
    fireEvent.change(nameInput, { target: { value: "Test" } });
    fireEvent.change(emailInput, { target: { value: "test@test.com" } });
    fireEvent.change(passwordInput, { target: { value: "password123" } });
    fireEvent.change(confirmInput, { target: { value: "password123" } });

    const submitBtn = screen.getByRole("button", { name: /criar conta/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockRouter.push).toHaveBeenCalledWith("/dashboard");
    });
  });

  it("shows loading state during submission", async () => {
    let resolveRegister: (v: { ok: boolean }) => void;
    mockRegister.mockReturnValue(
      new Promise((resolve) => {
        resolveRegister = resolve;
      })
    );
    render(<RegisterPage />);

    const nameInput = screen.getByLabelText("Nome");
    const emailInput = screen.getByLabelText("E-mail");
    const passwordInput = screen.getByLabelText("Senha");
    const confirmInput = screen.getByLabelText("Confirmar senha");
    fireEvent.change(nameInput, { target: { value: "Test" } });
    fireEvent.change(emailInput, { target: { value: "test@test.com" } });
    fireEvent.change(passwordInput, { target: { value: "password123" } });
    fireEvent.change(confirmInput, { target: { value: "password123" } });

    const submitBtn = screen.getByRole("button", { name: /criar conta/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByRole("button")).toHaveTextContent(/criando/i);
      expect(screen.getByRole("button")).toBeDisabled();
    });

    resolveRegister!({ ok: true });
  });

  it("redirects if already authenticated", async () => {
    mockUseSession.mockReturnValue({
      data: { user: { id: "1", email: "a@b.com", name: "A" } },
      status: "authenticated",
    });
    render(<RegisterPage />);

    await waitFor(() => {
      expect(mockRouter.replace).toHaveBeenCalledWith("/dashboard");
    });
  });
});
