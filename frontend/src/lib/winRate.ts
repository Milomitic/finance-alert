/* Soglia e formulazione del win rate, estratte da `PortfolioSummary.tsx`.
 * Non sono un componente: tenerle li' rompeva il Fast Refresh della scheda */

/** Percentuale minima di posizioni chiuse prima che un tasso sia un tasso.
 *  Stessa soglia gia' in uso in SetupsPage e DataHealthCard: sotto, il limite
 *  inferiore di Wilson al 95% e' cosi' basso che la percentuale non distingue
 *  una strategia buona da una mediocre. */
export const MIN_WIN_RATE_N = 20;

/** Cosa scrivere sotto le posizioni chiuse.
 *
 *  Tre stati, non due. Nulla di chiuso non e' "0%": e' una domanda a cui
 *  ancora non e' stata data risposta. Sotto le 20 chiusure si mostra la
 *  FRAZIONE, che dice esattamente altrettanto senza pretendere di piu' — a
 *  1 su 1 il limite inferiore di Wilson sta intorno al 21%, quindi "100%" e'
 *  compatibile con una strategia che perde quattro volte su cinque. E questa
 *  e' la pagina dei soldi veri, il posto peggiore per un numero che afferma
 *  piu' di quanto sappia. Vincolato da PortfolioSummary.test.tsx. */
export function winRateLabel(wins: number, closed: number): string {
  if (closed <= 0) return "—";
  if (closed < MIN_WIN_RATE_N) return `${wins}/${closed} chiuse in utile`;
  return `win rate ${Math.round((wins / closed) * 100)}%`;
}
