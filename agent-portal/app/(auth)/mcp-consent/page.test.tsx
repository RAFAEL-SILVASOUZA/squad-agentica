import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import McpConsentPage from "./page";

const { mockSearchParams, mockApiPost } = vi.hoisted(() => {
  const mockSearchParams = new URLSearchParams();
  const mockApiPost = vi.fn();
  return { mockSearchParams, mockApiPost };
});

vi.mock("next/navigation", () => ({
  useSearchParams: () => mockSearchParams,
}));

vi.mock("@/lib/api", () => ({
  api: {
    post: (...args: unknown[]) => mockApiPost(...args),
  },
}));

// Mock window.location.href with a getter/setter
let currentHref = "http://localhost/mcp-consent";
Object.defineProperty(window, "location", {
  writable: true,
  value: {
    ...window.location,
    get href() {
      return currentHref;
    },
    set href(val: string) {
      currentHref = val;
    },
  },
});

describe("McpConsentPage", () => {
  beforeEach(() => {
    mockApiPost.mockClear();
    currentHref = "http://localhost/mcp-consent";
    mockSearchParams.set("client_id", "my-client");
    mockSearchParams.set("client_name", "My MCP Client");
    mockSearchParams.set("redirect_uri", "http://localhost:3000/callback");
    mockSearchParams.set("scope", "tools:read tools:write");
    mockSearchParams.set("code_challenge", "abc123");
    mockSearchParams.set("code_challenge_method", "S256");
    mockSearchParams.set("state", "xyz789");
    mockSearchParams.set("resource", "https://mcp.example.com");
  });

  it("shows the client name", () => {
    render(<McpConsentPage />);
    expect(screen.getByText("My MCP Client")).toBeInTheDocument();
  });

  it("shows the scope", () => {
    render(<McpConsentPage />);
    expect(screen.getByText("tools:read tools:write")).toBeInTheDocument();
  });

  it("shows the redirect URI", () => {
    render(<McpConsentPage />);
    expect(screen.getByText("http://localhost:3000/callback")).toBeInTheDocument();
  });

  it("shows both Autorizar and Recusar buttons", () => {
    render(<McpConsentPage />);
    expect(screen.getByRole("button", { name: /autorizar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /recusar/i })).toBeInTheDocument();
  });

  it("clicking Recusar redirects with error=access_denied", () => {
    render(<McpConsentPage />);
    const denyBtn = screen.getByRole("button", { name: /recusar/i });
    fireEvent.click(denyBtn);

    expect(currentHref).toBe(
      "http://localhost:3000/callback?error=access_denied&state=xyz789"
    );
  });

  it("clicking Recusar without state omits state from redirect", () => {
    mockSearchParams.delete("state");
    render(<McpConsentPage />);
    const denyBtn = screen.getByRole("button", { name: /recusar/i });
    fireEvent.click(denyBtn);

    expect(currentHref).toBe("http://localhost:3000/callback?error=access_denied");
  });

  it("clicking Autorizar calls api.post and redirects with code", async () => {
    mockApiPost.mockResolvedValue({ code: "auth_code_123" });
    render(<McpConsentPage />);

    const authorizeBtn = screen.getByRole("button", { name: /autorizar/i });
    fireEvent.click(authorizeBtn);

    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith(
        "/api/mcp/consent",
        expect.objectContaining({
          client_id: "my-client",
          redirect_uri: "http://localhost:3000/callback",
          scope: "tools:read tools:write",
          code_challenge: "abc123",
          code_challenge_method: "S256",
          state: "xyz789",
          resource: "https://mcp.example.com",
        })
      );
    });

    await waitFor(() => {
      expect(currentHref).toBe(
        "http://localhost:3000/callback?code=auth_code_123&state=xyz789"
      );
    });
  });

  it("clicking Autorizar without state omits state from redirect", async () => {
    mockSearchParams.delete("state");
    mockApiPost.mockResolvedValue({ code: "auth_code_456" });
    render(<McpConsentPage />);

    const authorizeBtn = screen.getByRole("button", { name: /autorizar/i });
    fireEvent.click(authorizeBtn);

    await waitFor(() => {
      expect(currentHref).toBe("http://localhost:3000/callback?code=auth_code_456");
    });
  });

  it("shows error when api.post fails", async () => {
    mockApiPost.mockRejectedValue(new Error("Erro interno do servidor. Tente novamente."));
    render(<McpConsentPage />);

    const authorizeBtn = screen.getByRole("button", { name: /autorizar/i });
    fireEvent.click(authorizeBtn);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText("Erro interno do servidor. Tente novamente.")).toBeInTheDocument();
    });
  });

  it("shows loading state while authorizing", async () => {
    let resolvePost: (v: { code: string }) => void;
    mockApiPost.mockReturnValue(
      new Promise((resolve) => {
        resolvePost = resolve;
      })
    );
    render(<McpConsentPage />);

    const authorizeBtn = screen.getByRole("button", { name: /autorizar/i });
    fireEvent.click(authorizeBtn);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /autorizando/i })).toBeInTheDocument();
    });

    resolvePost!({ code: "done" });
  });
});
