/** Il costo vero di un piano su eToro (FA-126), da un preventivo eToro.
 *
 *  Il preventivo dice quanto costa APRIRE (commissione, ricarico, spread) e
 *  quanto costa una NOTTE (overnight). Quante notti dipende dalla tenuta
 *  attesa del piano: «Breve», «Medio», «Lungo», che `tradePlaybook` dichiara
 *  come «qualche giorno - 2 settimane», «2 - 6 settimane», «1 - 3 mesi». Qui
 *  si prende il MEZZO di ciascuna fascia, e lo si dice a schermo: e' una
 *  stima della durata, non una misura. */

/** Sedute di mercato al centro della tenuta attesa dichiarata. */
export const SEDUTE_TENUTA: Record<string, number> = { Breve: 7, Medio: 20, Lungo: 45 };

/** Le notti di calendario in N sedute: 5 sedute sono 7 notti. */
export function notti(sedute: number): number {
  return Math.round((sedute * 7) / 5);
}

export interface StimaCosti {
  apertura: number | null;
  detenzione: number | null;
  totale: number | null;
  notti: number;
  /** Il totale in % del margine investito. */
  pctMargine: number | null;
  /** Il totale in unita' di R: il rischio e' margine x leva x distanza dello stop. */
  inR: number | null;
  /** Quanto del margine si perde se scatta lo stop. */
  stopPctMargine: number;
}

export function stimaCosti(p: {
  aperturaUsd: number | null;
  notteUsd: number | null;
  tenuta: string;
  importo: number;
  leva: number;
  stopPct: number;
}): StimaCosti {
  const n = notti(SEDUTE_TENUTA[p.tenuta] ?? SEDUTE_TENUTA.Medio);
  const detenzione = p.notteUsd == null ? null : p.notteUsd * n;
  const totale = p.aperturaUsd == null || detenzione == null ? null : p.aperturaUsd + detenzione;
  const rischio = p.importo * p.leva * (p.stopPct / 100);
  return {
    apertura: p.aperturaUsd,
    detenzione,
    totale,
    notti: n,
    pctMargine: totale == null || p.importo <= 0 ? null : (totale / p.importo) * 100,
    inR: totale == null || rischio <= 0 ? null : totale / rischio,
    stopPctMargine: -p.stopPct * p.leva,
  };
}
