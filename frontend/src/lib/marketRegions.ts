import type { IndexBreadth } from "@/api/types";

/* Regional mood derivation, shared by every surface that summarises the market
 * by area. Extracted from MoodCard when the dashboard's mood hero became a
 * strip: the reasoning below is the expensive part and must not be duplicated
 * or re-derived by whoever writes the next summary widget.
 */

export type MoodKey = "bullish" | "neutral" | "bearish";

export interface RegionDef {
  code: "US" | "EU" | "ASIA";
  label: string;
  flagSrc: string | null;
  emoji?: string;
  /** Gli indici su cui si calcola il TOTALE della regione, e quindi il suo
   *  umore. ⚠️ Solo panieri che non si sovrappongono: vedi sotto. */
  indexCodes: string[];
  /** Le borse mostrate una per una sotto la regione, nell'ordine di lettura.
   *  Puo' contenere indici FUORI dal totale: si vedono, ma non si sommano. */
  shownCodes: string[];
}

/* ⚠️ Il totale di una regione si calcola su panieri DISGIUNTI.
 *
 * Fino al 2026-09-25 l'umore USA sommava S&P 500, Nasdaq 100 e Dow Jones: 635
 * «titoli», ma quasi tutti quelli del Nasdaq e tutti quelli del Dow sono gia'
 * nell'S&P, quindi i grandi nomi contavano due o tre volte. Finche' a schermo
 * c'era solo il totale non si vedeva; con le righe per borsa sotto, un «221
 * in rialzo» che e' la somma di righe sovrapposte si legge come 221 titoli, e
 * non lo e'.
 *
 * - USA: l'S&P 500 da solo. Contiene il Dow per intero e il Nasdaq 100 quasi
 *   per intero.
 * - Europa: Euro Stoxx 50 + FTSE 100, che non hanno un titolo in comune (il
 *   Regno Unito non e' nell'eurozona). Il FTSE MIB resta FUORI dal totale per
 *   la ragione di sempre: i suoi titoli maggiori — ENI, ENEL, ISP, UCG —
 *   stanno anche nell'Euro Stoxx, e sommarli spingerebbe il verdetto europeo
 *   verso l'Italia. Il FTSE 100 mancava perche' e' arrivato dopo quella
 *   scelta, non perche' fosse stato escluso.
 * - Asia: Giappone, Corea e Hong Kong, tre panieri distinti. Il Giappone per
 *   primo per scelta dell'utente (il Nikkei e' il riferimento asiatico della
 *   stampa italiana). La Cina continentale e' uscita dal catalogo nel 2026-05.
 */
export const REGIONS: RegionDef[] = [
  {
    code: "US", label: "USA", flagSrc: "/flags/us.svg",
    indexCodes: ["SP500"], shownCodes: ["SP500", "NDX", "DJI"],
  },
  {
    code: "EU", label: "Europa", flagSrc: "/flags/eu.svg",
    indexCodes: ["EUSTX50", "FTSE100"], shownCodes: ["EUSTX50", "FTSE100", "FTSEMIB"],
  },
  {
    code: "ASIA", label: "Asia", flagSrc: null, emoji: "🌏",
    indexCodes: ["N225", "KOSPI20", "HSI30"], shownCodes: ["N225", "KOSPI20", "HSI30"],
  },
];

export interface RegionMood {
  mood: MoodKey;
  pct_above_ema200: number;
  /** ⚠️ Esposta, e non piu' solo calcolata dentro `deriveMood` per decidere
   *  l'umore: tre regioni messe a confronto hanno senso se portano le STESSE
   *  misure, e la partecipazione di medio periodo e' quella che si muove
   *  prima. Era gia' qui dentro, semplicemente non usciva. */
  pct_above_ema50: number;
  advancers: number;
  decliners: number;
  avg_change: number;
  total_stocks: number;
}

export function deriveMood(indices: IndexBreadth[]): RegionMood {
  if (indices.length === 0) {
    return {
      mood: "neutral", pct_above_ema200: 0, pct_above_ema50: 0,
      advancers: 0, decliners: 0, avg_change: 0, total_stocks: 0,
    };
  }
  const totalN = indices.reduce((s, i) => s + i.n, 0);
  const weightedPct = totalN > 0
    ? indices.reduce((s, i) => s + (i.pct_above_ema200 ?? 0) * i.n, 0) / totalN
    : 0;
  // Medium-term breadth (EMA50), blended 50/50 with the long-term (EMA200)
  // for the mood decision — mirrors the backend derive_mood blend. EMA50 is
  // more responsive, so the mood reflects medium-term participation too, not
  // just the slow 200. (pct_above_ema200 is still reported for the EMA200 label.)
  const weightedPct50 = totalN > 0
    ? indices.reduce((s, i) => s + (i.pct_above_ema50 ?? 0) * i.n, 0) / totalN
    : 0;
  const breadth = 0.5 * weightedPct + 0.5 * weightedPct50;
  const advancers = indices.reduce((s, i) => s + i.advancers, 0);
  const decliners = indices.reduce((s, i) => s + i.decliners, 0);
  const weightedChange = totalN > 0
    ? indices.reduce((s, i) => s + (i.avg_change_pct ?? 0) * i.n, 0) / totalN
    : 0;
  let mood: MoodKey = "neutral";
  if (breadth >= 60 && advancers > decliners) mood = "bullish";
  else if (breadth <= 40 && decliners > advancers) mood = "bearish";
  return {
    mood, pct_above_ema200: weightedPct, pct_above_ema50: weightedPct50,
    advancers, decliners, avg_change: weightedChange, total_stocks: totalN,
  };
}

/** Le regioni di un'istantanea, nell'ordine di lettura, con sotto ciascuna le
 *  sue borse. `indices` segue `shownCodes`; un indice che l'istantanea non
 *  porta semplicemente manca, non diventa una riga di zeri. */
export function regionMoods(byIndex: IndexBreadth[]): Array<{
  region: RegionDef;
  mood: RegionMood;
  indices: Array<{ index: IndexBreadth; inTotal: boolean }>;
}> {
  const perCodice = new Map(byIndex.map((i) => [i.code, i]));
  return REGIONS.map((region) => ({
    region,
    mood: deriveMood(byIndex.filter((i) => region.indexCodes.includes(i.code))),
    indices: region.shownCodes
      .map((c) => perCodice.get(c))
      .filter((i): i is IndexBreadth => !!i && i.n > 0)
      .map((index) => ({ index, inTotal: region.indexCodes.includes(index.code) })),
  }));
}
