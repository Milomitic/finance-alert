import type { Fundamentals } from "@/api/types";

/** Sotto questa soglia (in %) la confidenza di un punteggio si mostra come
 *  avvertimento; sopra non si mostra (richiesta dell'utente, 2026-10-14).
 *  Un proprietario solo per le schede Stock Score e Valutazione tecnica. */
export const CONFIDENZA_BASSA = 50;

/** La soglia della scheda fondamentali e' piu' alta, per scelta dell'utente:
 *  misurata sul catalogo il 2026-10-14, 922 titoli su 998 stanno fra 90 e
 *  100%, 72 fra 75 e 89%, 4 fra 50 e 74% e nessuno sotto il 50%. Con la soglia
 *  delle altre schede non comparirebbe mai. */
export const CONFIDENZA_BASSA_FONDAMENTALI = 90;

const ANNI_ATTESI = 4;
const RIGHE_RECENTI = 4;

export interface Completezza {
  valore: number;
  presenti: number;
  attesi: number;
}

/** Quanta parte del bilancio che la scheda mostra esiste davvero.
 *
 *  - Il bilancio ANNUALE conta sempre: quattro anni di ricavi, utile netto e
 *    utile per azione, e un anno che manca pesa come tre valori assenti.
 *  - Trimestrali e risultati trimestrali contano solo se la sezione ESISTE.
 *    ⚠️ Molte societa' inglesi, francesi e di Hong Kong pubblicano conti
 *    semestrali: contare le loro trimestrali come mancanti dava a Hermes,
 *    Safran o Nexi il 43% con quattro anni di bilancio completi. Il buco vero
 *    e' un altro — 0016.HK senza ricavi negli ultimi due anni.
 *  - Dei risultati contano solo quelli PASSATI (data entro `oggi`): una
 *    trimestrale futura non ha ancora un utile riportato. */
export function completezzaFondamentali(
  f: Pick<Fundamentals, "annual" | "quarterly" | "earnings">,
  oggi: string,
): Completezza | null {
  const annual = [...f.annual].sort((a, b) => b.fiscal_year_end.localeCompare(a.fiscal_year_end)).slice(0, ANNI_ATTESI);
  const quarterly = [...f.quarterly]
    .sort((a, b) => b.fiscal_quarter_end.localeCompare(a.fiscal_quarter_end))
    .slice(0, RIGHE_RECENTI);
  const passati = f.earnings
    .filter((e) => e.date.slice(0, 10) <= oggi)
    .sort((a, b) => b.date.localeCompare(a.date))
    .slice(0, RIGHE_RECENTI);
  if (annual.length === 0 && quarterly.length === 0 && passati.length === 0) return null;

  const c = (v: number | null | undefined) => (v != null ? 1 : 0);
  let presenti = annual.reduce((n, r) => n + c(r.revenue) + c(r.net_income) + c(r.eps), 0);
  let attesi = ANNI_ATTESI * 3;
  if (quarterly.length) {
    presenti += quarterly.reduce((n, r) => n + c(r.revenue) + c(r.eps), 0);
    attesi += quarterly.length * 2;
  }
  if (passati.length) {
    presenti += passati.reduce((n, r) => n + c(r.eps_estimate) + c(r.eps_reported), 0);
    attesi += passati.length * 2;
  }
  return { valore: Math.round((presenti / attesi) * 100), presenti, attesi };
}
