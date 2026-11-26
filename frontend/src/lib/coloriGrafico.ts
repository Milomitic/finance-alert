/* ─── I colori disegnati nei grafici: un proprietario solo ─────────────────
 *
 * Un canvas o un SVG non leggono le classi Tailwind, quindi i grafici
 * scrivevano i colori a mano: 110 esadecimali in 16 file (B-13), tre verdi
 * diversi per «su» nello stesso grafico e il rosso dei guasti (`#dc2626`,
 * red-600) per ogni candela ribassista (B-11, B-62). CLAUDE.md dice
 * «rose/emerald = direzione, red = guasto»: valeva nelle classi e non qui.
 *
 * Modulo foglia, senza dipendenze, perche' lo importano componenti e lib
 * (la lezione di `app/indicators/periods.py`: una fonte unica che non si
 * puo' importare non e' una fonte unica). */

/** Emerald 600 dell'app (`tailwind.config.js` lo ridefinisce): il «su». */
export const SU = "#17b551";
/** Rose 600: il «giu'». Non il red-600 dei guasti. */
export const GIU = "#e11d48";
/** Ne' su ne' giu': variazione nulla, esito senza stima. */
export const NEUTRO = "#94a3b8";
/** Avviso, non direzione: la soglia di ipercomprato dell'RSI. */
export const AVVISO = "#d97706";

/** Un colore esadecimale `#rrggbb` con trasparenza, per volumi e istogrammi. */
export function conAlfa(hex: string, alfa: number): string {
  const n = Number.parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alfa})`;
}

/** Il colore della direzione di una variazione. */
export function coloreDirezione(v: number | null | undefined): string {
  if (v == null || v === 0) return NEUTRO;
  return v > 0 ? SU : GIU;
}

/** I colori predefiniti delle serie degli indicatori (B-65): la stessa EMA
 *  era viola chiaro in un grafico e viola pieno in un altro, e il MACD era
 *  rosso, il colore dei guasti, per una linea che non e' ne' un errore ne'
 *  una direzione. */
export const SERIE = {
  ema20: "#a855f7",
  ema50: "#3b82f6",
  ema200: "#f59e0b",
  bb: "#0ea5e9",
  rsi: "#7c3aed",
  macd: "#d946ef",
} as const;

/** Assi, griglia e bordi dei grafici canvas, per tema (FA-175, B-12, A-51).
 *  Erano scritti per il fondo chiaro: `#374151` su `#1a1a1a` vale 1,7:1, e la
 *  griglia nera al 5% spariva. Testo dell'asse sopra 4,5:1 in entrambi i
 *  temi: `#525252` su bianco ~7,8:1, `#a3a3a3` su `#1a1a1a` ~7,4:1. */
export interface ColoriAssi {
  testo: string;
  griglia: string;
  bordo: string;
}

export function coloriAssi(scuro: boolean): ColoriAssi {
  return scuro
    ? { testo: "#a3a3a3", griglia: "rgba(255,255,255,0.06)", bordo: "rgba(255,255,255,0.14)" }
    : { testo: "#525252", griglia: "rgba(0,0,0,0.05)", bordo: "rgba(0,0,0,0.12)" };
}

/** Le stesse in forma di opzioni di lightweight-charts, per `applyOptions`. */
export function opzioniAssi(scuro: boolean) {
  const c = coloriAssi(scuro);
  return {
    layout: { textColor: c.testo },
    grid: { vertLines: { color: c.griglia }, horzLines: { color: c.griglia } },
    rightPriceScale: { borderColor: c.bordo },
    timeScale: { borderColor: c.bordo },
  };
}

/** Il tema in questo momento, letto dal DOM (la classe di `useTheme`). */
export function temaScuroOra(): boolean {
  return typeof document !== "undefined" && document.documentElement.classList.contains("dark");
}
