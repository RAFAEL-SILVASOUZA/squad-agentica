export function normalize(s: string): string {
  return s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

export function matches(query: string, name: string): boolean {
  const q = normalize(query);
  if (q === "") return true;
  return normalize(name).includes(q);
}
