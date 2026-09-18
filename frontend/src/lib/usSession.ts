/* ─── L'orologio della sessione americana ────────────────────────────────── *
 *
 * Il cruscotto e' dedicato al pre-market e alle ore di Wall Street, ma l'utente
 * guarda da Roma: «apre fra un'ora» e' l'informazione, non «sono le 15:30».
 * Qui sta il solo calcolo che serve, PURO e senza rete, cosi' e' verificabile.
 *
 * ⚠️ Il fuso si chiede a `Intl`, mai all'orologio della macchina. E' la stessa
 * trappola che in questo repo ha fatto girare 17 job del backend due ore piu'
 * tardi per mesi (`CronTrigger` senza fuso esplicito, verde sul portatile a
 * Roma e sbagliato nel pod a UTC): una lettura basata su `getHours()` sarebbe
 * corretta solo sulla macchina di chi la scrive.
 *
 * ⚠️ E le FESTIVITA' NON sono modellate, di proposito. Una lista di date
 * scritta a mano invecchia in silenzio ed e' sbagliata esattamente quando
 * conta (il Dockerfile porta lo stesso ragionamento sui pacchetti da pinnare).
 * Quindi questo modulo dice l'OROLOGIO — quanto manca, dove siamo nella
 * finestra — e la FASE vera la dichiarano le quotazioni, che il 4 luglio
 * rispondono CLOSED da sole. Chi rende a schermo tiene le due cose distinte.
 */

export type UsPhase = "pre" | "open" | "after" | "closed";

/** Minuti dalla mezzanotte di New York. Il pre-market di Nasdaq/NYSE apre alle
 *  04:00 ET ed e' la finestra che yfinance marca `PRE`; l'after hours chiude
 *  alle 20:00 ET. */
export const PRE_OPEN_MIN = 4 * 60;
export const RTH_OPEN_MIN = 9 * 60 + 30;
export const RTH_CLOSE_MIN = 16 * 60;
export const AFTER_CLOSE_MIN = 20 * 60;

export interface UsSessionClock {
  /** Minuti dalla mezzanotte a New York (0..1439). */
  etMinutes: number;
  /** "09:41" a New York. */
  etLabel: string;
  /** 0 = domenica … 6 = sabato, a New York. */
  etWeekday: number;
  /** Sabato o domenica a New York: nessuna seduta, nemmeno il pre-market. */
  weekend: boolean;
  /** La fase secondo il SOLO orologio (festivita' escluse — vedi sopra). */
  phase: UsPhase;
  /** Cosa succede dopo: "apertura", "chiusura", "pre-market"… */
  nextLabel: string;
  /** Minuti al prossimo passaggio, SOLO se cade nello stesso giorno di New
   *  York. Null altrimenti: attraversare la mezzanotte e i cambi d'ora e' un
   *  altro conto, e un numero sbagliato qui sarebbe invisibile a chi legge. */
  minutesToNext: number | null;
  /** Il giorno del prossimo passaggio quando non e' oggi ("lunedì", "domani").
   *  Null quando `minutesToNext` c'e'. */
  nextDayLabel: string | null;
  /** Avanzamento dentro la finestra corrente, 0..1. Null a mercato chiuso,
   *  dove non esiste nessuna finestra in corso da riempire. */
  progress: number | null;
}

const GIORNI = ["domenica", "lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato"];
const INDICE_GIORNO: Record<string, number> = {
  Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6,
};

/* Un solo formatter, costruito una volta: `Intl.DateTimeFormat` e' caro da
 * istanziare e questo modulo viene chiamato a ogni battito dell'orologio.
 *
 * ⚠️ `hourCycle: "h23"` non e' pignoleria: con `hour12: false` alcune versioni
 * di ICU rendono la mezzanotte come «24», e `24 * 60` metterebbe l'orologio un
 * giorno intero fuori dalla finestra — un difetto che compare solo fra le
 * 00:00 e le 00:59 di New York. */
const FORMATTER = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  weekday: "short",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** Ora di New York, presa dal calendario IANA (cambi d'ora compresi). */
export function etWallClock(now: Date): { minutes: number; label: string; weekday: number } {
  const parts = FORMATTER.formatToParts(now);
  const leggi = (tipo: string) => parts.find((p) => p.type === tipo)?.value ?? "";
  const h = parseInt(leggi("hour"), 10) % 24;
  const m = parseInt(leggi("minute"), 10);
  const ore = Number.isFinite(h) ? h : 0;
  const minuti = Number.isFinite(m) ? m : 0;
  return {
    minutes: ore * 60 + minuti,
    label: `${String(ore).padStart(2, "0")}:${String(minuti).padStart(2, "0")}`,
    weekday: INDICE_GIORNO[leggi("weekday")] ?? 0,
  };
}

function frazione(t: number, da: number, a: number): number {
  return Math.min(1, Math.max(0, (t - da) / (a - da)));
}

export function usSessionClock(now: Date): UsSessionClock {
  const { minutes: t, label, weekday } = etWallClock(now);
  const weekend = weekday === 0 || weekday === 6;
  const base = { etMinutes: t, etLabel: label, etWeekday: weekday, weekend };

  if (weekend) {
    // Sabato la prossima apertura e' lunedi'; domenica e' domani.
    return {
      ...base, phase: "closed", nextLabel: "pre-market",
      minutesToNext: null, nextDayLabel: weekday === 6 ? "lunedì" : "domani", progress: null,
    };
  }
  if (t < PRE_OPEN_MIN) {
    return {
      ...base, phase: "closed", nextLabel: "pre-market",
      minutesToNext: PRE_OPEN_MIN - t, nextDayLabel: null, progress: null,
    };
  }
  if (t < RTH_OPEN_MIN) {
    return {
      ...base, phase: "pre", nextLabel: "apertura",
      minutesToNext: RTH_OPEN_MIN - t, nextDayLabel: null,
      progress: frazione(t, PRE_OPEN_MIN, RTH_OPEN_MIN),
    };
  }
  if (t < RTH_CLOSE_MIN) {
    return {
      ...base, phase: "open", nextLabel: "chiusura",
      minutesToNext: RTH_CLOSE_MIN - t, nextDayLabel: null,
      progress: frazione(t, RTH_OPEN_MIN, RTH_CLOSE_MIN),
    };
  }
  if (t < AFTER_CLOSE_MIN) {
    return {
      ...base, phase: "after", nextLabel: "fine after hours",
      minutesToNext: AFTER_CLOSE_MIN - t, nextDayLabel: null,
      progress: frazione(t, RTH_CLOSE_MIN, AFTER_CLOSE_MIN),
    };
  }
  // Dopo le 20:00 ET: il prossimo pre-market e' domani, o lunedi' se e' venerdi'.
  return {
    ...base, phase: "closed", nextLabel: "pre-market",
    minutesToNext: null, nextDayLabel: weekday === 5 ? "lunedì" : "domani", progress: null,
  };
}

/** «1h 12m», «48m». Il conto alla rovescia si legge a colpo d'occhio, quindi
 *  niente secondi: sotto il minuto dice «meno di un minuto» invece di 0m. */
export function formatDelta(minutes: number): string {
  if (!Number.isFinite(minutes) || minutes < 0) return "—";
  if (minutes < 1) return "meno di un minuto";
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return h > 0 ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}m`;
}

/* Il GIORNO di New York in forma ISO. Serve perche' un'agenda della seduta
 * americana si chiude a mezzanotte a New York, non a Roma: alle 01:00 italiane
 * a Wall Street sono ancora le 19:00 del giorno prima, e chiedere «gli eventi
 * di oggi» col calendario locale salterebbe l'intera serata americana. */
const FORMATTER_GIORNO = new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/New_York",
  year: "numeric", month: "2-digit", day: "2-digit",
});

/** "2026-09-18" secondo il calendario di New York. */
export function etToday(now: Date): string {
  // en-CA rende gia' AAAA-MM-GG: nessuna ricomposizione a mano dei pezzi, che
  // e' il punto in cui si sbaglia l'ordine dei campi.
  return FORMATTER_GIORNO.format(now);
}

/** Il giorno di New York in italiano, per le etichette assolute. */
export function etGiorno(weekday: number): string {
  return GIORNI[weekday] ?? "";
}
