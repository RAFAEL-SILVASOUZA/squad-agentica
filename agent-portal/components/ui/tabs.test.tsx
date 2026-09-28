import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Tabs } from "./tabs";

const tabs = [
  { id: "tab1", label: "Tab 1" },
  { id: "tab2", label: "Tab 2" },
  { id: "tab3", label: "Tab 3" },
];

describe("Tabs", () => {
  it("links tabs to the panel when idPrefix is given", () => {
    render(<Tabs tabs={tabs} activeTab="tab2" onTabChange={() => {}} idPrefix="mon" />);
    const tab = screen.getByRole("tab", { name: "Tab 2" });
    expect(tab).toHaveAttribute("id", "mon-tab-tab2");
    expect(tab).toHaveAttribute("aria-controls", "mon-panel");
  });

  it("renders all tabs", () => {
    render(<Tabs tabs={tabs} activeTab="tab1" onTabChange={() => {}} />);
    expect(screen.getByRole("tab", { name: "Tab 1" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Tab 2" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Tab 3" })).toBeInTheDocument();
  });

  it("marks active tab with aria-selected", () => {
    render(<Tabs tabs={tabs} activeTab="tab2" onTabChange={() => {}} />);
    expect(screen.getByRole("tab", { name: "Tab 2" })).toHaveAttribute(
      "aria-selected",
      "true"
    );
    expect(screen.getByRole("tab", { name: "Tab 1" })).toHaveAttribute(
      "aria-selected",
      "false"
    );
  });

  it("calls onTabChange when a tab is clicked", () => {
    const onTabChange = vi.fn();
    render(<Tabs tabs={tabs} activeTab="tab1" onTabChange={onTabChange} />);
    fireEvent.click(screen.getByRole("tab", { name: "Tab 2" }));
    expect(onTabChange).toHaveBeenCalledWith("tab2");
  });

  it("applies accent color to active tab", () => {
    render(<Tabs tabs={tabs} activeTab="tab1" onTabChange={() => {}} />);
    const activeTab = screen.getByRole("tab", { name: "Tab 1" });
    expect(activeTab).toHaveStyle({ color: "var(--accent)" });
  });
});
