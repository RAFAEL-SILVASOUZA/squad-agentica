import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import HomePage from "./page";

describe("HomePage (scaffold)", () => {
  it("renders the Agent Portal heading", () => {
    render(<HomePage />);
    expect(screen.getByRole("heading", { name: /agent portal/i })).toBeInTheDocument();
  });
});
