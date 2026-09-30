import { describe, it, expect } from "vitest";
import { normalize, matches } from "./utils";

describe("normalize", () => {
  it("remove acentos e converte para minúsculas", () => {
    expect(normalize("Especificações")).toBe("especificacoes");
  });

  it("preserva espaços e converte para minúsculas", () => {
    expect(normalize("MCP Servers")).toBe("mcp servers");
  });
});

describe("matches", () => {
  it("ignora acento e caixa", () => {
    expect(matches("especif", "Redator de Especificações")).toBe(true);
  });

  it("query vazia casa com qualquer nome", () => {
    expect(matches("", "anything")).toBe(true);
  });

  it("não casa quando a query não é subcadena", () => {
    expect(matches("xyz", "abc")).toBe(false);
  });
});
