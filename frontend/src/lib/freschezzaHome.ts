/* ─── L'eta' massima dei dati della home (FA-179, fase A) ──────────────────
 *
 * La home non mostra un numero piu' vecchio della sua eta' massima: al suo
 * posto lo scheletro, finche' arriva quello nuovo. Prima una scheda ripresa
 * dopo giorni mostrava i dati di allora per 15 secondi. Le eta' sono una
 * scelta dichiarata, non il caso del timer. */

export interface QueryCritica {
  chiave: readonly unknown[];
  etaMassimaMs: number;
}

export const QUERY_CRITICHE_HOME: readonly QueryCritica[] = [
  // Prezzi e mercato si muovono di minuto in minuto.
  { chiave: ["live-assets"], etaMassimaMs: 2 * 60_000 },
  { chiave: ["etoro", "vivo"], etaMassimaMs: 2 * 60_000 },
  // Riepilogo e mercato derivano dalle scansioni: cambiano di ora in ora.
  { chiave: ["dashboard", "summary"], etaMassimaMs: 15 * 60_000 },
  { chiave: ["dashboard", "market-summary"], etaMassimaMs: 15 * 60_000 },
];

/** Le query critiche il cui dato esiste ma e' oltre l'eta' massima. Un dato
 *  ASSENTE non e' «vecchio»: lo gestisce il caricamento normale. E una query
 *  il cui ultimo tentativo e' FALLITO dopo quel dato non trattiene la pagina:
 *  lo scheletro resterebbe per sempre, mentre la scheda sa dire il guasto. */
export function queryScadute(
  stato: (chiave: readonly unknown[]) => { dataUpdatedAt: number; errorUpdatedAt?: number; data?: unknown } | undefined,
  ora: number,
  critiche: readonly QueryCritica[] = QUERY_CRITICHE_HOME,
): QueryCritica[] {
  return critiche.filter((c) => {
    const s = stato(c.chiave);
    if (s == null || s.data === undefined || s.dataUpdatedAt <= 0) return false;
    if ((s.errorUpdatedAt ?? 0) > s.dataUpdatedAt) return false;
    return ora - s.dataUpdatedAt > c.etaMassimaMs;
  });
}
