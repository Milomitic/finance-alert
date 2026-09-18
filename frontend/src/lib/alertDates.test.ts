import { describe, expect, it } from "vitest";

import {
  DELAYED_DETECTION_MIN_DAYS,
  alertDelayDays,
  daysBetween,
  detectionInstant,
  formatShortDate,
  isAlertDelayed,
  isDelayedDetection,
} from "@/lib/alertDates";

describe("daysBetween", () => {
  it("returns 0 for the same calendar day even with different times", () => {
    // Midday UTC so the calendar day is the same in any test-runner tz.
    expect(daysBetween("2026-07-06T12:00:00Z", "2026-07-06")).toBe(0);
  });

  it("counts whole calendar days between the two dates", () => {
    expect(daysBetween("2026-07-08", "2026-07-06")).toBe(2);
    expect(daysBetween("2026-07-10T09:00:00Z", "2026-07-06")).toBe(4);
  });

  it("returns null when either side is missing or unparsable", () => {
    expect(daysBetween(null, "2026-07-06")).toBeNull();
    expect(daysBetween("2026-07-06", undefined)).toBeNull();
    expect(daysBetween("not-a-date", "2026-07-06")).toBeNull();
  });
});

describe("isDelayedDetection", () => {
  // Threshold raised 1 → 4 (audit 2026-07-08): a weekend gap (~2 days) plus
  // one skipped scan is NORMAL cadence, not a delay worth an orange chip.
  it(`fires only at >= ${DELAYED_DETECTION_MIN_DAYS} calendar days`, () => {
    // Same day / normal cadence → no chip.
    expect(isDelayedDetection("2026-07-06T18:00:00Z", "2026-07-06")).toBe(false);
    expect(isDelayedDetection("2026-07-07", "2026-07-06")).toBe(false);
    // Friday close → Monday scan (weekend ≈ 2-3 days) → still no chip.
    expect(isDelayedDetection("2026-07-06", "2026-07-03")).toBe(false);
    // 4+ days = real backfill/outage → chip.
    expect(isDelayedDetection("2026-07-10", "2026-07-06")).toBe(true);
    expect(isDelayedDetection("2026-07-20", "2026-07-06")).toBe(true);
  });

  it("never fires for legacy alerts without a signal_date", () => {
    expect(isDelayedDetection("2026-07-06T18:00:00Z", null)).toBe(false);
    expect(isDelayedDetection("2026-07-06T18:00:00Z", undefined)).toBe(false);
  });
});

describe("formatShortDate", () => {
  it("formats an ISO date as DD/MM/YY and tolerates missing values", () => {
    expect(formatShortDate("2026-07-06")).toBe("06/07/26");
    expect(formatShortDate(null)).toBe("—");
    expect(formatShortDate(undefined)).toBe("—");
  });
});

/* ─── La rilevazione è la PRIMA emissione, non l'ultima revisione ────────── *
 *
 * ⚠️ Un alert è una riga VIVA: finché il segnale persiste, ogni scansione lo
 * rivede e riscrive `triggered_at`. Misurato in produzione il 2026-09-18 su
 * 8.736 alert: 80% ne ha almeno una revisione, 73% ha una prima emissione
 * anteriore a `triggered_at`, e un alert FICO ne conta 103 — mostrava «+10g
 * di ritardo» su un segnale rilevato la sera stessa della candela.
 *
 * Il difetto è sistematico per detector, non casuale: colpisce quelli la cui
 * ancora è un evento FISSO nel passato (squeeze_expansion 91% di pastiglie
 * contro 25% di ritardi veri, gap_and_go 80% contro 26%) e risparmia quelli
 * la cui ancora avanza a ogni scansione (trend_pullback 4% contro 1%). Il
 * commento nel motore lo dichiarava impossibile: «signal_date + triggered_at
 * advance together». Per un'ancora fissa non avanzano insieme.
 */
describe("l'istante della rilevazione", () => {
  const conPrimaEmissione = {
    triggered_at: "2026-09-14T19:40:56Z",
    signal_date: "2026-09-04",
    snapshot: { first_emitted_at: "2026-09-04T23:32:22Z", amend_count: 103 },
  };

  it("usa la prima emissione quando c'è", () => {
    expect(detectionInstant(conPrimaEmissione)).toBe("2026-09-04T23:32:22Z");
  });

  it("il caso FICO non porta più la pastiglia", () => {
    // Dieci giorni da `triggered_at`, zero o uno dalla prima emissione.
    // ⚠️ Si asserisce la PASTIGLIA e non il conteggio: la prima emissione vera
    // era alle 23:32 UTC, che a Roma è l'una del giorno dopo, quindi il conteggio
    // in giorni di calendario vale 0 in CI e 1 in locale. È la trappola che
    // questo repo documenta — un test sui giorni fra due date è vacuo in UTC.
    // La pastiglia non cambia: sotto la soglia di 4 in entrambi i fusi.
    expect(isAlertDelayed(conPrimaEmissione)).toBe(false);
  });

  it("conta i giorni dalla prima emissione, non dall'ultima revisione", () => {
    // Mezzogiorno UTC: il giorno di calendario è lo stesso in qualunque fuso,
    // che è la convenzione già adottata in questo file.
    expect(alertDelayDays({
      triggered_at: "2026-09-14T12:00:00Z",
      signal_date: "2026-09-04",
      snapshot: { first_emitted_at: "2026-09-06T12:00:00Z" },
    })).toBe(2);
  });

  it("un ritardo VERO continua a portarla", () => {
    /* Le tre divergenze hanno un ritardo vero al 100%: un pivot si conferma
     * solo alcune barre dopo essersi formato, quindi quel segnale non PUÒ
     * esistere il giorno della candela. Lì la pastiglia dice il vero. */
    const divergenza = {
      triggered_at: "2026-09-14T19:40:56Z",
      signal_date: "2026-09-04",
      snapshot: { first_emitted_at: "2026-09-10T12:00:00Z" },
    };
    expect(isAlertDelayed(divergenza)).toBe(true);
    expect(alertDelayDays(divergenza)).toBe(6);
  });

  it("senza prima emissione ripiega su triggered_at", () => {
    // I 116 alert (1,3%) che precedono il campo: è il meglio disponibile.
    const storico = { triggered_at: "2026-09-14T19:40:56Z", signal_date: "2026-09-04" };
    expect(detectionInstant(storico)).toBe("2026-09-14T19:40:56Z");
    expect(isAlertDelayed(storico)).toBe(true);
  });

  it("uno snapshot malformato non fa esplodere niente", () => {
    for (const snapshot of [null, undefined, { first_emitted_at: 42 }, { first_emitted_at: "" }]) {
      const a = { triggered_at: "2026-09-14T19:40:56Z", signal_date: "2026-09-04", snapshot };
      expect(detectionInstant(a as never)).toBe("2026-09-14T19:40:56Z");
    }
  });
});
