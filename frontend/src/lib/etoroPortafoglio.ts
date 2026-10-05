import type { EtoroPosizione } from "@/api/etoro";

/** Le posizioni eToro raggruppate per strumento (FA-124).
 *
 *  Su eToro si apre spesso piu' volte lo stesso titolo: il conto vero del
 *  2026-10-05 aveva 19 posizioni su 9 strumenti. Una riga per posizione
 *  ripeterebbe quattro volte SOXL e nasconderebbe quanto pesa davvero; una
 *  riga per strumento somma margine, esposizione e P/L, e il dettaglio resta a
 *  un tocco.
 *
 *  ⚠️ Le somme sono di numeri che eToro ha gia' calcolato nella valuta del
 *  conto: sommarli e' corretto. Il prezzo medio d'apertura invece NON si
 *  calcola qui — pesarlo sulle unita' darebbe un numero plausibile e diverso
 *  dal «prezzo medio» di eToro, che conta anche il cambio d'apertura. */
export interface GruppoStrumento {
  instrumentId: number;
  simbolo: string | null;
  nome: string | null;
  ticker: string | null;
  valuta: string | null;
  /** "long", "short", o "misto" se convivono. */
  lato: "long" | "short" | "misto";
  /** Le leve presenti, in ordine crescente. */
  leve: number[];
  regolamenti: string[];
  posizioni: EtoroPosizione[];
  margineUsd: number | null;
  esposizioneUsd: number | null;
  pnlUsd: number | null;
  pnlPctMargine: number | null;
  /** Lo stop che costa di piu', in % del margine della sua posizione. */
  stopPeggiorePct: number | null;
  /** Posizioni senza stop: su un CFD a leva e' l'informazione che conta. */
  senzaStop: number;
  ancheManuale: boolean;
}

function somma(valori: (number | null)[]): number | null {
  const noti = valori.filter((v): v is number => v != null && Number.isFinite(v));
  return noti.length ? noti.reduce((a, b) => a + b, 0) : null;
}

export function raggruppaPerStrumento(aperte: readonly EtoroPosizione[]): GruppoStrumento[] {
  const perId = new Map<number, EtoroPosizione[]>();
  for (const p of aperte) {
    const l = perId.get(p.instrument_id) ?? [];
    l.push(p);
    perId.set(p.instrument_id, l);
  }
  const gruppi: GruppoStrumento[] = [];
  for (const [instrumentId, lista] of perId) {
    const posizioni = [...lista].sort((a, b) => a.aperta_il.localeCompare(b.aperta_il));
    const primo = posizioni[0];
    const lati = new Set(posizioni.map((p) => p.lato));
    const margine = somma(posizioni.map((p) => p.margine_usd));
    const pnl = somma(posizioni.map((p) => p.pnl_usd));
    const stopPct = posizioni.map((p) => p.stop_pct_margine).filter((v): v is number => v != null);
    gruppi.push({
      instrumentId,
      simbolo: primo.simbolo,
      nome: primo.nome,
      ticker: primo.ticker,
      valuta: primo.valuta,
      lato: lati.size > 1 ? "misto" : primo.lato,
      leve: [...new Set(posizioni.map((p) => p.leva))].sort((a, b) => a - b),
      regolamenti: [...new Set(posizioni.map((p) => p.regolamento))],
      posizioni,
      margineUsd: margine,
      esposizioneUsd: somma(posizioni.map((p) => p.esposizione_usd)),
      pnlUsd: pnl,
      pnlPctMargine: pnl != null && margine ? (pnl / margine) * 100 : null,
      stopPeggiorePct: stopPct.length ? Math.min(...stopPct) : null,
      senzaStop: posizioni.filter((p) => p.stop == null).length,
      ancheManuale: posizioni.some((p) => p.anche_manuale),
    });
  }
  // Il peso vero di uno strumento a leva e' l'esposizione, non il margine.
  return gruppi.sort((a, b) => Math.abs(b.esposizioneUsd ?? 0) - Math.abs(a.esposizioneUsd ?? 0));
}

/** «Long ×5 CFD», «Long ×1 reale», «misto ×2–5». */
export function etichettaLato(g: Pick<GruppoStrumento, "lato" | "leve" | "regolamenti">): string {
  const lato = g.lato === "long" ? "Long" : g.lato === "short" ? "Short" : "Misto";
  const leva = g.leve.length === 1 ? `×${g.leve[0]}` : `×${g.leve[0]}–${g.leve[g.leve.length - 1]}`;
  const reg = g.regolamenti.length === 1 ? ` ${g.regolamenti[0] === "cfd" ? "CFD" : g.regolamenti[0]}` : "";
  return `${lato} ${leva}${reg}`;
}

export function fmtPct(v: number | null | undefined, decimali = 1): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const r = Number(v.toFixed(decimali));
  return `${r > 0 ? "+" : ""}${r.toFixed(decimali)}%`;
}
