import * as React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { GitHubIntegration } from "./github-integration";
import { ToastProvider } from "@/components/ui/toast";
import { ApiError } from "@/lib/api";

// ─── Mocks ───────────────────────────────────────────────────────────────────

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockDelete = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
    list: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    status: number;
    code: string;
    details?: Record<string, unknown>;
    constructor(status: number, body: { error: string; code: string; details?: Record<string, unknown> }) {
      super(body.error);
      this.status = status;
      this.code = body.code;
      this.details = body.details;
    }
  },
}));

function renderIntegration() {
  return render(
    <ToastProvider>
      <GitHubIntegration />
    </ToastProvider>
  );
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe("GitHubIntegration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet.mockResolvedValue({ connected: false });
  });

  it("renders loading state on initial load", () => {
    mockGet.mockReturnValue(new Promise(() => {}));
    renderIntegration();
    expect(screen.getByText(/carregando status/i)).toBeInTheDocument();
  });

  it("renders disconnected state when not connected", async () => {
    renderIntegration();
    await waitFor(() => {
      expect(screen.getByText("Desconectado")).toBeInTheDocument();
    });
    expect(screen.getByLabelText("Token GitHub")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /conectar/i })).toBeInTheDocument();
  });

  it("renders connected state with username when connected", async () => {
    mockGet.mockResolvedValue({ connected: true, username: "octocat" });
    renderIntegration();
    await waitFor(() => {
      expect(screen.getByText(/conectado como/i)).toBeInTheDocument();
    });
    expect(screen.getByText("octocat")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /testar conexão/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /desconectar/i })).toBeInTheDocument();
  });

  it("connects with token and updates status", async () => {
    mockPost.mockResolvedValue(undefined);
    mockGet.mockResolvedValueOnce({ connected: false }).mockResolvedValueOnce({ connected: true, username: "octocat" });
    renderIntegration();
    await waitFor(() => {
      expect(screen.getByLabelText("Token GitHub")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Token GitHub"), { target: { value: "ghp_test123" } });
    fireEvent.click(screen.getByRole("button", { name: /conectar/i }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/integrations/github/connect", { token: "ghp_test123" });
    });
    await waitFor(() => {
      expect(screen.getByText(/conectado como/i)).toBeInTheDocument();
    });
  });

  it("shows error when token is empty", async () => {
    renderIntegration();
    await waitFor(() => {
      expect(screen.getByLabelText("Token GitHub")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /conectar/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/token é obrigatório/i);
    });
    expect(mockPost).not.toHaveBeenCalled();
  });

  it("shows API error on connect failure", async () => {
    mockPost.mockRejectedValue(
      new ApiError(401, { error: "auth_failed", code: "invalid_token", details: { error: "Token inválido" } })
    );
    renderIntegration();
    await waitFor(() => {
      expect(screen.getByLabelText("Token GitHub")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Token GitHub"), { target: { value: "ghp_invalid" } });
    fireEvent.click(screen.getByRole("button", { name: /conectar/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/token inválido/i);
    });
  });

  it("tests connection when connected", async () => {
    mockGet.mockResolvedValue({ connected: true, username: "octocat" });
    mockPost.mockResolvedValue({ success: true, message: "OK" });
    renderIntegration();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /testar conexão/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /testar conexão/i }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/api/integrations/github/test");
    });
  });

  it("disconnects and updates status", async () => {
    mockGet.mockResolvedValueOnce({ connected: true, username: "octocat" }).mockResolvedValueOnce({ connected: false });
    mockDelete.mockResolvedValue(undefined);
    renderIntegration();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /desconectar/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /desconectar/i }));

    await waitFor(() => {
      expect(mockDelete).toHaveBeenCalledWith("/api/integrations/github");
    });
    await waitFor(() => {
      expect(screen.getByText("Desconectado")).toBeInTheDocument();
    });
  });
});
