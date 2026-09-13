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
