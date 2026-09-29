/**
 * Tempo relativo curto ("agora", "há 12 min", "há 3 h", "há 2 dias").
 * `now` é opcional para facilitar testes com data fixa.
 */
const MIN = 60_000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

export function relativeTime(iso: string, now?: Date): string {
  const ref = now ?? new Date();
  const delta = ref.getTime() - new Date(iso).getTime();

  if (delta < MIN) return "agora";
  if (delta < HOUR) return `há ${Math.floor(delta / MIN)} min`;
  if (delta < DAY) return `há ${Math.floor(delta / HOUR)} h`;
  return `há ${Math.floor(delta / DAY)} dias`;
}
