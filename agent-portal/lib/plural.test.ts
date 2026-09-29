import { describe, it, expect } from "vitest";
import { plural, formatCount } from "./plural";

describe("plural", () => {
  it("usa singular só para 1", () => {
    expect(plural(0, "agente", "agentes")).toBe("0 agentes");
    expect(plural(1, "agente", "agentes")).toBe("1 agente");
    expect(plural(2, "agente", "agentes")).toBe("2 agentes");
    expect(plural(1234, "agente", "agentes")).toBe("1.234 agentes");
  });

  it("formatCount usa separador pt-BR", () => {
    expect(formatCount(1234567)).toBe("1.234.567");
  });
});
