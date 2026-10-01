import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import MCPServerPage from "@/app/(dashboard)/mcp/server/page";
import { api } from "@/lib/api";
import { AppSidebar } from "@/components/layout/app-sidebar";

vi.mock("@/lib/api", () => ({
  api: {
    get: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock("@/components/ui", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/ui")>();
  return {
    ...actual,
    useToast: () => ({ addToast: vi.fn() }),
  };
});

vi.mock("next/navigation", () => ({
  usePathname: () => "/mcp/server",
}));

describe("MCPServerPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Mock for tokens
    (api.get as any).mockImplementation((path: string) => {
      if (path === "/api/mcp/tokens") {
        return Promise.resolve([
          {
            jti: "1",
            client_name: "Claude Desktop",
            scope: "read",
            created_at: new Date().toISOString(),
            expires_at: new Date().toISOString(),
            revoked_at: null,
          },
        ]);
      }
      if (path === "/api/mcp/tools") {
        return Promise.resolve([
          { name: "get_weather", description: "Get current weather" },
        ]);
      }
      return Promise.resolve([]);
    });
  });

  it("renders the MCP URL and the Copy button", async () => {
    render(<MCPServerPage />);
    
    await waitFor(() => {
      expect(screen.getByText("http://localhost/mcp/mcp")).toBeDefined();
    });
    expect(screen.getByRole("button", { name: /copiar/i })).toBeDefined();
  });

  it("renders the token list", async () => {
    render(<MCPServerPage />);
    
    await waitFor(() => {
      // "Ativo" (badge de status) e "Revogar" (botão) são únicos ao token list.
      expect(screen.getByText(/Ativo/i)).toBeDefined();
      expect(screen.getByText(/Revogar/i)).toBeDefined();
    }, { timeout: 3000 });
  });

  it("renders the tools list", async () => {
    render(<MCPServerPage />);
    
    await waitFor(() => {
      expect(screen.getByText(/get_weather/i)).toBeDefined();
      expect(screen.getByText(/Get current weather/i)).toBeDefined();
    }, { timeout: 3000 });
  });
});

describe("AppSidebar MCP Link", () => {
  it("contains the Servidor MCP link", () => {
    render(<AppSidebar />);
    expect(screen.getByText("Servidor MCP")).toBeDefined();
    const link = screen.getByRole("link", { name: /Servidor MCP/ });
    expect(link.getAttribute("href")).toBe("/mcp/server");
  });
});
