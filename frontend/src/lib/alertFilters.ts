/* Lettura dei filtri Segnali dalla query string. Vive fuori dalla pagina
 * perche' un segnalibro sopravvive alla UI che l'ha prodotto — e perche' una
 * pagina che esporta anche una funzione rompe il Fast Refresh */

import type { AlertListParams } from "@/api/alerts";

/** Exported for tests: the stale-parameter handling below is invisible on
 *  screen — a dropped filter looks exactly like no filter — so it needs a
 *  test that reads the behaviour directly. */
export function filtersFromSearch(sp: URLSearchParams): AlertListParams {
  const s = (k: string) => sp.get(k) || undefined;
  return {
    archived: sp.get("archived") === "true",
    // Vedi `STATUS_OPTIONS` in AlertFilters: quasi ogni esito maturato vive su
    // un alert archiviato, quindi «attivi e archiviati» e' l'unico modo di
    // leggere la colonna Esito — e va nell'URL come ogni altro filtro,
    // altrimenti un segnalibro riaprirebbe una lista diversa da quella
    // condivisa.
    include_archived: sp.get("include_archived") === "true" || undefined,
    ticker: s("ticker"),
    q: s("q"),
    rule_kind: s("rule_kind"),
    tone: s("tone"),
    nature: s("nature"),
    outcome: s("outcome"),
    horizon: s("horizon"),
    date_from: s("date_from"),
    date_to: s("date_to"),
    strength_min: numParam(sp, "strength_min"),
    // `probability_min` is deliberately NOT read back from the URL. The filter
    // was removed (see AlertFilters), but a bookmark or a pasted link from
    // before the removal still carries the parameter — and honouring it would
    // apply a filter with no control to see or clear it. Worse, Probabilità
    // tops out at 52 across the whole engine, so any saved threshold above
    // that returns an empty list forever with nothing on screen explaining
    // why. Dropping it degrades an old link to "no filter", which is the only
    // safe reading.
  };
}

/** Parse a 0-100 numeric param; anything else → undefined (ignored). */
function numParam(sp: URLSearchParams, key: string): number | undefined {
  const raw = sp.get(key);
  if (raw == null || raw === "") return undefined;
  const n = Number(raw);
  return Number.isFinite(n) && n >= 0 && n <= 100 ? n : undefined;
}

/* ─── URL ⇄ state (filters + sort + page) ────────────────────────────────
 *
 * The working set (filters, sort, page) is serialized into the URL search
 * params so back-navigation and shared links restore exactly what the user
 * was looking at. Only non-default values are written, keeping URLs short.
 * AlertListParams is flat strings/numbers, so the mapping is 1:1.
 */

/** ⚠️ Le chiavi che QUESTA vista possiede, e solo quelle.
 *
 * Dal 2026-09-19 i segnali sono una scheda fra tre, e le altre due scrivono
 * nello stesso URL: `vista` dice quale scheda e' aperta, `tono`/`condizione`/
 * `pagina`/`esiti`/`gara` appartengono a «In formazione» e «Esiti». La
 * serializzazione qui sotto ricostruiva la query da zero, quindi il primo
 * render della lista cancellava `vista` e la scheda rimbalzava su se stessa —
 * un difetto che si presenta come «la scheda non si apre» e si cerca ovunque
 * tranne che in un `useEffect` di sincronizzazione.
 *
 * Si riparte dai parametri CORRENTI, si tolgono le chiavi proprie e si
 * riscrivono quelle non di default: cosi' i filtri di una scheda sopravvivono
 * al passaggio su un'altra e tornare indietro ritrova la lista com'era. */
const CHIAVI_PROPRIE = [
  "ticker", "q", "rule_kind", "tone", "nature", "outcome", "horizon",
  "date_from", "date_to", "strength_min", "archived", "include_archived",
  "page", "sort_by", "sort_dir",
] as const;

export function searchFromState(
  filters: AlertListParams,
  page: number,
  sortBy: string,
  sortDir: "asc" | "desc",
  correnti: URLSearchParams,
): URLSearchParams {
  const sp = new URLSearchParams(correnti);
  for (const k of CHIAVI_PROPRIE) sp.delete(k);
  if (filters.ticker) sp.set("ticker", filters.ticker);
  if (filters.q) sp.set("q", filters.q);
  if (filters.rule_kind) sp.set("rule_kind", filters.rule_kind);
  if (filters.tone) sp.set("tone", filters.tone);
  if (filters.nature) sp.set("nature", filters.nature);
  if (filters.outcome) sp.set("outcome", filters.outcome);
  if (filters.horizon) sp.set("horizon", filters.horizon);
  if (filters.date_from) sp.set("date_from", filters.date_from);
  if (filters.date_to) sp.set("date_to", filters.date_to);
  if (filters.strength_min != null) sp.set("strength_min", String(filters.strength_min));
  if (filters.archived) sp.set("archived", "true");
  if (filters.include_archived) sp.set("include_archived", "true");
  if (page > 0) sp.set("page", String(page + 1)); // 1-based in the URL
  if (sortBy !== "triggered_at") sp.set("sort_by", sortBy);
  if (sortDir !== "desc") sp.set("sort_dir", sortDir);
  return sp;
}

/** Il filtro Esito e' attivo, ma la lista sta guardando solo i segnali NON
 *  archiviati — cioe' quasi nessuno di quelli che un esito ce l'hanno.
 *
 *  ⚠️ Non e' una preferenza di visualizzazione: `archive_concluded_alerts`
 *  archivia un segnale appena il suo esito matura E la data e' uscita dalla
 *  finestra delle confluenze (7 giorni). Per ogni detector con orizzonte da 21
 *  o 63 sedute le due condizioni diventano vere nella STESSA passata di
 *  scansione, perche' la maturazione gira subito prima dell'archiviazione.
 *  Misurato in produzione: 5.312 dei 5.313 esiti maturati stanno su alert
 *  archiviati. Chiedere «Azzeccato» fra i soli attivi restituisce quindi una
 *  manciata di righe, e quel numero descrive la regola di archiviazione, non
 *  il motore. */
export function esitoNascostoDallArchivio(f: AlertListParams): boolean {
  return !!f.outcome && !f.include_archived && !f.archived;
}
