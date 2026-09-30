import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BottomNav } from "./bottom-nav";

// Mock do next/navigation para usarPathname
const mockUsePathname = vi.fn();
vi.mock("next/navigation", () => ({
  usePathname: () => mockUsePathname(),
}));

describe("BottomNav", () => {
  beforeEach(() => {
    mockUsePathname.mockReturnValue("/");
  });

  it("renderiza os 4 itens: Início, Pipelines, Aprovações e Mais", () => {
    render(<BottomNav pendingApprovals={0} onOpenSidebar={() => {}} />);
    expect(screen.getByRole("link", { name: /início/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /pipelines/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /aprovações/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /mais/i })).toBeInTheDocument();
  });

  it("item ativo tem aria-current=page", () => {
    mockUsePathname.mockReturnValue("/pipelines");
    render(<BottomNav pendingApprovals={0} onOpenSidebar={() => {}} />);
    expect(screen.getByRole("link", { name: /pipelines/i })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /início/i })).not.toHaveAttribute("aria-current");
  });

  it("Início está ativo na raiz", () => {
    mockUsePathname.mockReturnValue("/");
    render(<BottomNav pendingApprovals={0} onOpenSidebar={() => {}} />);
    expect(screen.getByRole("link", { name: /início/i })).toHaveAttribute("aria-current", "page");
  });

  it("Aprovações mostra badge com contagem", () => {
    render(<BottomNav pendingApprovals={3} onOpenSidebar={() => {}} />);
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("Aprovações não mostra badge com 0", () => {
    render(<BottomNav pendingApprovals={0} onOpenSidebar={() => {}} />);
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("Mais chama onOpenSidebar", () => {
    const onOpenSidebar = vi.fn();
    render(<BottomNav pendingApprovals={0} onOpenSidebar={onOpenSidebar} />);
    fireEvent.click(screen.getByRole("button", { name: /mais/i }));
    expect(onOpenSidebar).toHaveBeenCalled();
  });

  it("cada item tem altura mínima de 44px", () => {
    render(<BottomNav pendingApprovals={0} onOpenSidebar={() => {}} />);
    const links = screen.getAllByRole("link");
    const buttons = screen.getAllByRole("button");
    for (const item of [...links, ...buttons]) {
      const style = item.getAttribute("style") ?? "";
      expect(style).toMatch(/min-height:\s*44px|height:\s*44px/);
    }
  });
});
