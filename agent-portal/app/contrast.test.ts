// Teste de contraste WCAG (AA, 4.5:1): lê globals.css e calcula a razão
// de luminosidade de --text-secondary/--text-muted sobre --bg e --bg-card,
// nos seletores dos temas escuro (padrão) e claro.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, it, expect } from "vitest";

// Extrai o corpo da regra de um seletor (contando chaves). Busca por linha
// exata ("seletor {") para não pegar comentários que citam o seletor.
function blockText(css: string, selector: string) {
  const lines = css.split(/\r?\n/);
  const startLine = lines.findIndex((l) => l.trim() === selector + " {");
  if (startLine === -1) throw new Error(`regra ${selector} não encontrada`);
  let depth = 0;
  const body: string[] = [];
  for (let i = startLine; i < lines.length; i++) {
    for (const ch of lines[i]) {
      if (ch === "{") depth++;
      if (ch === "}") {
        depth--;
        if (depth === 0) return body.join("\n");
      }
    }
    body.push(lines[i]);
  }
  throw new Error(`regra ${selector} incompleta`);
}

// Busca "--nome: #HEX" sem regex (o bloco CSS do tema pode ter CRLF; um
// simples indexOf + slice evita qualquer problema de escape de classe
// de caracteres no ambiente de teste).
function hex(css: string, block: string, name: string) {
  const text = blockText(css, block);
  const key = "--" + name + ":";
  const at = text.indexOf(key);
  if (at === -1) throw new Error(`${name} não encontrado em ${block}`);
  const rest = text.slice(at + key.length);
  const hash = rest.indexOf("#");
  if (hash === -1) throw new Error(`${name} sem valor em ${block}`);
  return rest.slice(hash, hash + 7);
}

function lum(h: string) {
  const c = [1, 3, 5]
    .map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}

const ratio = (a: string, b: string) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};

const css = readFileSync(join(__dirname, "globals.css"), "utf8");

for (const block of ['[data-theme="dark"]', '[data-theme="light"]']) {
  for (const fg of ["text-secondary", "text-muted"]) {
    for (const bg of ["bg", "bg-card"]) {
      it(`${block} ${fg} sobre ${bg} ≥ 4.5`, () =>
        expect(ratio(hex(css, block, fg), hex(css, block, bg))).toBeGreaterThanOrEqual(
          4.5
        )
      );
    }
  }
}
