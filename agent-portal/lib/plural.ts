/**
 * Plural pt-BR (regra simples de 1/N).
 * Contagens exibidas no portal usam sempre formatCount, com separador pt-BR.
 */
export function formatCount(n: number): string {
  return n.toLocaleString("pt-BR");
}

export function plural(n: number, singular: string, pluralForm: string): string {
  return `${formatCount(n)} ${n === 1 ? singular : pluralForm}`;
}
