/**
 * Helpers for rendering an Alert's two timestamps:
 *   - signal_date: market-data bar where the indicator condition matched
 *   - triggered_at: wall-clock moment the alert row was created
 *
 * These are usually within a few hours of each other (scan runs end of
 * day, processes today's close), but can diverge meaningfully:
 *   - Backfill / first scan after an outage: signal Friday, triggered Monday
 *   - Weekend gap: signal Friday close, triggered following Monday
 *   - Manual scan after market close: signal today, triggered today
 *
 * The UI surfaces both so the user can tell when a "fresh-looking" alert
 * actually refers to old market data.
 */

/** Format an ISO date "YYYY-MM-DD" or full datetime string as a short
 *  Italian date (DD/MM/YY). Tolerates both forms: signal_date arrives as
 *  "YYYY-MM-DD" from the backend (Date column), triggered_at as full
 *  ISO 8601 with timezone. */
export function formatShortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("it-IT", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  });
}

/** Number of full days between two ISO dates/datetimes. Floored toward
 *  zero so "same calendar day" = 0 even when the times differ within
 *  the day. */
export function daysBetween(
  laterIso: string | null | undefined,
  earlierIso: string | null | undefined,
): number | null {
  if (!laterIso || !earlierIso) return null;
  const a = new Date(laterIso).getTime();
  const b = new Date(earlierIso).getTime();
  if (Number.isNaN(a) || Number.isNaN(b)) return null;
  // Compare calendar days using local-tz date strings; avoids spurious
  // 1-day deltas from time-of-day differences (e.g. signal at 22:00 UTC
  // vs triggered at 02:00 UTC the next day in local time).
  const dayA = new Date(a).toLocaleDateString("en-CA"); // YYYY-MM-DD
  const dayB = new Date(b).toLocaleDateString("en-CA");
  if (dayA === dayB) return 0;
  const ms = Date.parse(dayA) - Date.parse(dayB);
  return Math.round(ms / (1000 * 60 * 60 * 24));
}

/** Calendar-day delta above which detection counts as "in ritardo".
 *  Was 1 — but the daily scan legitimately lands 1-3 calendar days after
 *  the bar (weekend ≈ 2 days + one skipped scan), so ~93% of alerts wore
 *  the orange chip and it stopped meaning anything (alarm fatigue, audit
 *  2026-07-08). 4+ days can't be explained by a weekend alone → a real
 *  backfill / outage worth flagging. The exact +Ng delta stays visible in
 *  the tooltip regardless of the chip. */
export const DELAYED_DETECTION_MIN_DAYS = 4;

/** True when the system noticed an alert noticeably later than the signal
 *  date (>= DELAYED_DETECTION_MIN_DAYS calendar days). Used to highlight
 *  stale-detection cases in the UI so a user doesn't think "fresh alert"
 *  when the underlying bar is days old. */
export function isDelayedDetection(
  triggeredAt: string | null | undefined,
  signalDate: string | null | undefined,
): boolean {
  const d = daysBetween(triggeredAt, signalDate);
  return d != null && d >= DELAYED_DETECTION_MIN_DAYS;
}

/* ─── Quando il sistema ha NOTATO il segnale ─────────────────────────────── *
 *
 * ⚠️ Non è `triggered_at`, che sembra questo campo e non lo è.
 *
 * Un alert è una riga VIVA: finché il segnale persiste, ogni scansione lo
 * rivede e riscrive `triggered_at` insieme a `trigger_price`. Misurato in
 * produzione il 2026-09-18 su 8.736 alert: 7.010 (80%) hanno almeno una
 * revisione, 6.345 (73%) hanno una prima emissione anteriore a
 * `triggered_at`, e un alert FICO ne contava 103 — mostrava «rilevato in
 * ritardo di 10 giorni» su un segnale notato la sera stessa della candela.
 *
 * Il difetto è sistematico per detector e non casuale: colpisce quelli la cui
 * ancora è un evento FISSO nel passato — squeeze_expansion 91% di pastiglie
 * contro 25% di ritardi veri, gap_and_go 80% contro 26% — e risparmia quelli
 * la cui ancora avanza a ogni scansione, trend_pullback 4% contro 1%. Il
 * motore lo dichiarava impossibile in un commento («signal_date + triggered_at
 * advance together»): per un'ancora fissa non avanzano insieme.
 *
 * ⚠️ E la soglia di 4 giorni resta dov'è. Era stata ALZATA da 1 nel luglio
 * 2026 perché il 93% degli alert portava la pastiglia — una cura del sintomo,
 * visto che la causa era il campo. Ma la ragione scritta allora («il weekend
 * più una scansione saltata valgono 1-3 giorni») è vera proprio di QUESTA
 * misura, quindi ora quel 4 è giustificato invece che tirato.
 */
type AlertDatabile = {
  triggered_at: string;
  signal_date?: string | null;
  snapshot?: Record<string, unknown> | null;
};

/** L'istante della PRIMA emissione, col ripiego su `triggered_at` per i 116
 *  alert (1,3%) che precedono il campo — il meglio disponibile, non una
 *  ricostruzione. */
export function detectionInstant(alert: AlertDatabile): string {
  const grezzo = alert.snapshot?.["first_emitted_at"];
  return typeof grezzo === "string" && grezzo.length >= 10 ? grezzo : alert.triggered_at;
}

/* ─── La data UNICA in evidenza ──────────────────────────────────────────── *
 *
 * Un alert porta tre date e non sono la stessa cosa:
 *
 *   1. la BARRA su cui la regola ha fatto match (`signal_date`), che per i
 *      detector di stato viene ririmessa sull'ultima barra a ogni revisione —
 *      4.775 alert su 7.296 rivisti ce l'hanno diversa dalla nascita, fino a
 *      nove giorni dopo;
 *   2. il GIORNO in cui l'alert è comparso, dove sono fissati il prezzo
 *      d'ingresso e la geometria del piano;
 *   3. l'ultima osservazione (`triggered_at`), che avanza finché il segnale
 *      persiste.
 *
 * In evidenza va la (2), e la ragione è che è l'unica di cui si possa fare
 * qualcosa: è il giorno della barra a cui appartiene il prezzo d'ingresso.
 * Misurato in produzione il 2026-09-22: quel prezzo coincide al centesimo con
 * la chiusura di quella barra in 8.892 casi su 8.910. Le altre due restano
 * dove rispondono a una domanda loro — la (1) nella pastiglia «in ritardo»,
 * la (3) in una riga secondaria del dialogo quando è diversa.
 *
 * ⚠️ Si prende la DATA DEL TESTO, non il giorno locale dell'istante. Le
 * scansioni girano alle 23:32 UTC: convertito in ora italiana quell'istante
 * cade il giorno DOPO, cioè un giorno dopo la barra su cui il piano è
 * costruito — che è esattamente la confusione che questa data unica chiude.
 */

/** Il giorno in cui l'alert è comparso, come "YYYY-MM-DD". */
export function giornoDelSegnale(alert: AlertDatabile): string {
  return detectionInstant(alert).slice(0, 10);
}

/** La barra del match, quando è un giorno DIVERSO da quello di nascita: il
 *  fatto che la pastiglia «in ritardo» misura, e l'unico posto in cui
 *  `signal_date` merita ancora di comparire. */
export function barraDiversaDalSegnale(alert: AlertDatabile): string | null {
  const bar = alert.signal_date;
  return bar && bar.slice(0, 10) !== giornoDelSegnale(alert) ? bar.slice(0, 10) : null;
}

/** I giorni di calendario fra la barra del segnale e la rilevazione VERA. */
export function alertDelayDays(alert: AlertDatabile): number | null {
  return daysBetween(detectionInstant(alert), alert.signal_date);
}

/** ⚠️ Da preferire SEMPRE a `isDelayedDetection` su un alert intero: tiene la
 *  scelta del campo in un posto solo. Con tre chiamanti che passavano
 *  `triggered_at` a mano, il quarto avrebbe ricominciato da capo. */
export function isAlertDelayed(alert: AlertDatabile): boolean {
  return isDelayedDetection(detectionInstant(alert), alert.signal_date);
}
