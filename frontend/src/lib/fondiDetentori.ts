import type { TickerHolder } from "@/api/types";

/* ─── Chi detiene un titolo: i numeri della scheda dei fondi (2026-10-12) ───
 *
 * La scheda mostrava due cose che si sovrapponevano: una tabella dell'ULTIMA
 * operazione (Add / Reduce / Nuovo) e, sotto, le barre delle posizioni. Ma la
 * domanda di chi apre la pagina e' un'altra: chi lo detiene, quanto pesa nel
 * suo portafoglio, quanto vale in tutto. `value_usd` e `portfolio_pct` sono la
 * posizione INTERA nell'ultima dichiarazione, non il movimento; il movimento
 * resta, ma come contorno della riga.
 */

export interface Riepilogo {
  fondi: number;
  /** La somma delle posizioni dichiarate, in dollari. */
  valoreTotale: number | null;
  aumentano: number;
  riducono: number;
  nuovi: number;
  /** La data di dichiarazione piu' frequente: quasi sempre lo stesso trimestre. */
  periodo: string | null;
}

export function riepilogo(fondi: readonly TickerHolder[]): Riepilogo {
  const valori = fondi.map((h) => h.value_usd).filter((v): v is number => v != null);
  const conteggio = new Map<string, number>();
  for (const h of fondi) conteggio.set(h.period_end_date, (conteggio.get(h.period_end_date) ?? 0) + 1);
  const periodo = [...conteggio.entries()].sort((a, b) => b[1] - a[1] || b[0].localeCompare(a[0]))[0]?.[0] ?? null;
  return {
    fondi: fondi.length,
    valoreTotale: valori.length ? valori.reduce((a, b) => a + b, 0) : null,
    aumentano: fondi.filter((h) => h.action === "add").length,
    riducono: fondi.filter((h) => h.action === "reduce").length,
    nuovi: fondi.filter((h) => h.action === "new").length,
    periodo,
  };
}

export type Ordine = "peso" | "valore";

/** Per peso nel portafoglio o per valore, i dati mancanti in fondo. */
export function ordina(fondi: readonly TickerHolder[], ordine: Ordine): TickerHolder[] {
  const chiave = (h: TickerHolder) => (ordine === "peso" ? h.portfolio_pct : h.value_usd) ?? -1;
  return [...fondi].sort((a, b) => chiave(b) - chiave(a));
}

export interface Variazione {
  testo: string;
  tono: "su" | "giu" | "fermo";
  /** A parole, per chi non vede il colore e per il nome accessibile. */
  spiegazione: string;
}

/** Il movimento dell'ultimo trimestre, nella forma piu' informativa che c'e':
 *  il peso in punti se noto, se no la variazione delle azioni. */
export function variazione(h: TickerHolder): Variazione | null {
  if (h.action === "new") return { testo: "nuovo", tono: "su", spiegazione: "posizione nuova nell'ultimo trimestre" };
  const pp = h.portfolio_weight_delta_pp;
  if (pp != null && Number.isFinite(pp)) {
    const corpo = Math.abs(pp).toFixed(1);
    if (Number(corpo) === 0) return { testo: "=", tono: "fermo", spiegazione: "peso invariato" };
    return {
      testo: `${pp > 0 ? "+" : "−"}${corpo} pp`,
      tono: pp > 0 ? "su" : "giu",
      spiegazione: `peso ${pp > 0 ? "aumentato" : "ridotto"} di ${corpo} punti nell'ultimo trimestre`,
    };
  }
  const az = h.shares_change_pct;
  if (az != null && Number.isFinite(az) && Math.round(az) !== 0) {
    return {
      testo: `${az > 0 ? "+" : "−"}${Math.abs(az).toFixed(0)}% az.`,
      tono: az > 0 ? "su" : "giu",
      spiegazione: `azioni ${az > 0 ? "aumentate" : "ridotte"} del ${Math.abs(az).toFixed(0)}%`,
    };
  }
  if (h.action === "hold") return { testo: "=", tono: "fermo", spiegazione: "posizione invariata" };
  return null;
}
