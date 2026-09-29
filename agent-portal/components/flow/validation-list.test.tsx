import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ValidationList } from "./validation-list";

describe("ValidationList", () => {
  it("lists errors and selects the node or edge on click", () => {
    const onSelect = vi.fn();
    render(
      <ValidationList
        errors={[
          { rule: 8, message: '"Revisor" é um nó órfão', nodeId: "n2" },
          { rule: 1, message: "mapeamento incompleto", edgeId: "e1" },
        ]}
        onSelect={onSelect}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /nó órfão/ }));
    expect(onSelect).toHaveBeenCalledWith({ nodeId: "n2" });
    fireEvent.click(screen.getByRole("button", { name: /mapeamento incompleto/ }));
    expect(onSelect).toHaveBeenCalledWith({ edgeId: "e1" });
  });

  it("renders errors without a target as plain text", () => {
    render(<ValidationList errors={[{ rule: 3, message: "sem entrada" }]} onSelect={() => {}} />);
    expect(screen.getByText("sem entrada")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
