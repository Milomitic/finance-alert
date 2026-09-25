/* ─── Il VIX letto come movimento atteso ──────────────────────────────────── *
 *
 * Il VIX e' la volatilita' implicita ANNUALIZZATA dell'S&P 500 sui prossimi 30
 * giorni di calendario, in punti percentuali. Un «15,68» da solo non dice
 * niente a chi non fa il conto; tradotto in «l'S&P si muove di ±1% in una
 * seduta tipica» dice quanto e' normale il movimento che si ha davanti.
 *
 * ⚠️ E' UNA deviazione standard: il mercato si aspetta di restare dentro
 * l'intervallo circa due sedute su tre, non sempre. Chi lo mostra lo deve
 * dire, altrimenti un'uscita dall'intervallo si legge come un evento raro
 * quando capita una seduta su tre.
 *
 * ⚠️ E vale per l'S&P 500, non per il Nasdaq o il Dow: il VIX si calcola sulle
 * sue opzioni. Applicarlo agli altri due sarebbe un numero plausibile e
 * sbagliato.
 */

/** Sedute di borsa in un anno: la convenzione con cui si passa dalla
 *  volatilita' annua a quella di UNA seduta. */
const SEDUTE_ANNO = 252;
/** Il VIX guarda 30 giorni di CALENDARIO, non di borsa. */
const GIORNI_VIX = 30;

/** Il movimento atteso dell'S&P 500 in una seduta, in punti percentuali
 *  (una deviazione standard). Null se il VIX non e' un numero positivo. */
export function movimentoSeduta(vix: number | null | undefined): number | null {
  if (vix == null || !Number.isFinite(vix) || vix <= 0) return null;
  return vix / Math.sqrt(SEDUTE_ANNO);
}

/** Il movimento atteso sui 30 giorni che il VIX descrive, in punti
 *  percentuali (una deviazione standard). */
export function movimentoTrentaGiorni(vix: number | null | undefined): number | null {
  if (vix == null || !Number.isFinite(vix) || vix <= 0) return null;
  return vix * Math.sqrt(GIORNI_VIX / 365);
}

/** L'intervallo di prezzo atteso per una seduta, attorno alla chiusura
 *  PRECEDENTE — la variazione del giorno si misura da li', quindi anche
 *  l'intervallo. */
export function intervalloSeduta(
  chiusuraPrecedente: number | null | undefined,
  vix: number | null | undefined,
): { basso: number; alto: number } | null {
  const m = movimentoSeduta(vix);
  if (m == null || chiusuraPrecedente == null || !Number.isFinite(chiusuraPrecedente) || chiusuraPrecedente <= 0) {
    return null;
  }
  return { basso: chiusuraPrecedente * (1 - m / 100), alto: chiusuraPrecedente * (1 + m / 100) };
}

/** Quante volte il movimento atteso vale la variazione di oggi. */
export function multiploAtteso(
  variazione: number | null | undefined,
  vix: number | null | undefined,
): number | null {
  const m = movimentoSeduta(vix);
  if (m == null || variazione == null || !Number.isFinite(variazione)) return null;
  return Math.abs(variazione) / m;
}

export type BandaVix = "calmo" | "normale" | "teso" | "stress";

/** Le soglie convenzionali dei livelli del VIX. Non e' una previsione, ed e'
 *  per questo che stanno scritte nel suggerimento accanto al numero. */
export const SOGLIE_VIX: ReadonlyArray<{ banda: BandaVix; fino: number | null }> = [
  { banda: "calmo", fino: 15 },
  { banda: "normale", fino: 20 },
  { banda: "teso", fino: 30 },
  { banda: "stress", fino: null },
];

export function bandaVix(v: number): BandaVix {
  for (const s of SOGLIE_VIX) if (s.fino == null || v < s.fino) return s.banda;
  return "stress";
}

/** Letterali, per il purger di Tailwind. Calmo e normale restano neutri: sono
 *  lo stato ordinario, e colorarli li farebbe leggere come una notizia. */
export const CLASSE_BANDA: Record<BandaVix, string> = {
  calmo: "bg-muted text-muted-foreground",
  normale: "bg-muted text-muted-foreground",
  teso: "bg-amber-100 text-amber-800 dark:bg-amber-900/60 dark:text-amber-200",
  stress: "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300",
};

/** ⚠️ Il colore della variazione del VIX e' INVERTITO rispetto a un prezzo.
 *  In questa app rosa e verde dicono se il mercato va giu' o su: un VIX che
 *  sale e' il mercato che compra protezione, cioe' la stessa notizia di un
 *  indice che scende. Colorarlo come un prezzo farebbe leggere «bene» un
 *  rialzo della paura. */
export function tonoVariazioneVix(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v) || Number(v.toFixed(2)) === 0) return "text-muted-foreground";
  return v > 0 ? "text-rose-600 dark:text-rose-400" : "text-emerald-800 dark:text-emerald-400";
}

/** Un percento senza segno, con la virgola: «0,99». */
export function formatPercento(v: number, decimali = 2): string {
  return v.toLocaleString("it-IT", { minimumFractionDigits: decimali, maximumFractionDigits: decimali });
}

/** Il suggerimento sulle bande, coi movimenti CALCOLATI dalla stessa
 *  funzione che fa il numero a schermo: una tabella scritta a mano
 *  divergerebbe dal conto al primo ritocco. */
export function spiegazioneBande(): string {
  const pct = (livello: number) => formatPercento(movimentoSeduta(livello)!, 1);
  let prec: number | null = null;
  const righe = SOGLIE_VIX.map(({ banda, fino }) => {
    let testo: string;
    if (prec == null) testo = `sotto ${fino} ${banda} (S&P entro ±${pct(fino!)}% a seduta)`;
    else if (fino == null) testo = `sopra ${prec} ${banda} (S&P oltre ±${pct(prec)}% a seduta)`;
    else testo = `${prec}-${fino} ${banda} (S&P ±${pct(prec)}-${pct(fino)}% a seduta)`;
    prec = fino;
    return testo;
  });
  return righe.join(" · ");
}
