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
  if (h.action === "hold") return { testo: "Invariata", tono: "fermo", spiegazione: "quote invariate nell’ultimo trimestre" };
  if (h.action === "new") return { testo: "nuovo", tono: "su", spiegazione: "posizione nuova nell'ultimo trimestre" };
  const pp = h.portfolio_weight_delta_pp;
  if (pp != null && Number.isFinite(pp)) {
    const corpo = Math.abs(pp).toFixed(1);
    if (Number(corpo) === 0) return { testo: "=", tono: "fermo", spiegazione: "peso invariato" };
    return {
      testo: `${pp > 0 ? "+" : "−"}${corpo.replace(".", ",")}%`,
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
  return null;
}

/** Le ultime operazioni: la dichiarazione piu' recente prima, e a parita' di
 *  data la posizione piu' grande. */
export function ordinaPerData(fondi: readonly TickerHolder[]): TickerHolder[] {
  return [...fondi].sort(
    (a, b) => b.period_end_date.localeCompare(a.period_end_date) || (b.value_usd ?? -1) - (a.value_usd ?? -1),
  );
}

/** Sotto questa soglia una posizione e' un dettaglio: la scheda le mostra a
 *  richiesta. */
export const SOGLIA_PRINCIPALI_USD = 10e6;

/** Le posizioni da mostrare subito e quelle a richiesta. Se nessuna arriva
 *  alla soglia si mostrano tutte: una lista vuota con «mostra altri» sotto
 *  nasconderebbe proprio quello che c'e'. */
export function separaPerValore(
  fondi: readonly TickerHolder[],
  soglia = SOGLIA_PRINCIPALI_USD,
): { principali: TickerHolder[]; altri: TickerHolder[] } {
  const principali = fondi.filter((h) => (h.value_usd ?? 0) >= soglia);
  if (principali.length === 0) return { principali: [...fondi], altri: [] };
  return { principali, altri: fondi.filter((h) => (h.value_usd ?? 0) < soglia) };
}

/** Lo spostamento di peso di un'OPERAZIONE (aumento, riduzione). «=» resta
 *  dell'invariata soltanto: prima un peso arrotondato a un decimale scriveva
 *  «=» anche su una riduzione vera, perche' per un fondo gigante AXON pesa lo
 *  0,1% e una vendita lo sposta di centesimi (segnalato il 2026-11-26). Sotto
 *  un decimo si scrivono due decimali, sotto un centesimo «<0,01%». */
export function pesoOperazione(h: TickerHolder): Variazione | null {
  if (h.action === "hold") return { testo: "=", tono: "fermo", spiegazione: "posizione invariata" };
  const pp = h.portfolio_weight_delta_pp;
  if (pp == null || !Number.isFinite(pp)) return variazione(h);
  const segno = pp > 0 ? "+" : pp < 0 ? "−" : h.action === "reduce" ? "−" : "+";
  const tono = segno === "+" ? "su" : "giu";
  const a = Math.abs(pp);
  const corpo = a >= 0.1 ? a.toFixed(1) : a >= 0.005 ? a.toFixed(2) : null;
  const testo = corpo == null ? `${segno}<0,01%` : `${segno}${corpo.replace(".", ",")}%`;
  return { testo, tono, spiegazione: `peso nel portafoglio ${segno === "+" ? "aumentato" : "ridotto"} di ${corpo ?? "meno di 0,01"} punti` };
}
