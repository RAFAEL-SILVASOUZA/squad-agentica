import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { AppShell } from "./app-shell";

// Mocks
vi.mock("next-auth/react", () => ({
  useSession: () => ({ data: { user: { name: "Test User" } } }),
  signOut: vi.fn(),
}));
vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));
vi.mock("@/components/command-palette/use-shortcuts", () => ({
  useShortcuts: vi.fn(),
}));
vi.mock("@/lib/create-pipeline", () => ({
  useCreatePipelineAndNavigate: () => vi.fn(),
}));
vi.mock("@/components/command-palette/command-palette", () => ({
  CommandPalette: () => null,
}));
vi.mock("@/components/command-palette/shortcuts-help", () => ({
  ShortcutsHelp: () => null,
}));

describe("AppShell", () => {
  it("não mostra BottomNav em desktop (>= 768px)", async () => {
    Object.defineProperty(window, "innerWidth", { value: 1200, configurable: true });
    render(<AppShell pendingApprovals={0}>conteúdo</AppShell>);
    // Aguarda o useEffect de resize rodar
    await waitFor(() => {
      expect(screen.queryByRole("navigation", { name: /navegação inferior/i })).not.toBeInTheDocument();
    });
  });

  it("mostra BottomNav em mobile (< 768px)", async () => {
    Object.defineProperty(window, "innerWidth", { value: 390, configurable: true });
    render(<AppShell pendingApprovals={2}>conteúdo</AppShell>);
    await waitFor(() => {
      expect(screen.getByRole("navigation", { name: /navegação inferior/i })).toBeInTheDocument();
    });
  });

  it("mostra badge de aprovações na BottomNav em mobile", async () => {
    Object.defineProperty(window, "innerWidth", { value: 390, configurable: true });
    render(<AppShell pendingApprovals={5}>conteúdo</AppShell>);
    const nav = await screen.findByRole("navigation", { name: /navegação inferior/i });
    expect(nav).toHaveTextContent("5");
  });
});
