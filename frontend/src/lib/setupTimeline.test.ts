import { describe, expect, it } from "vitest";

import type { Setup } from "@/hooks/useSetups";
import { conversionBarNote, conversionStep } from "@/lib/setupTimeline";

const base = {
  id: 1, ticker: "BMY", name: null, detector: "sr_flip", tone: "bull",
  proximity: 0.8, convenience: 70, missing: "-", status: "converted",
} as unknown as Setup;

describe("conversionStep", () => {
  it("non dice niente di un setup non convertito", () => {
    expect(conversionStep({ ...base, status: "expired" })).toBeNull();
    expect(conversionStep({ ...base, status: "active" })).toBeNull();
  });

  it("un evento registrato con esito sopra il mercato", () => {
    const p = conversionStep({
      ...base, converted_signal_date: "2026-09-15", bar_lead_days: 4,
      outcome_signal_date: "2026-09-15", outcome_horizon_days: 21,
      outcome_mkt_neutral_hit: 1, outcome_mkt_neutral_excess_pct: 1.24,
    });
    expect(p).toEqual({
      evento: "evento 15 set (4g dopo l'apertura)",
      esito: "sopra il mercato a 21g (+1,2%)",
      tono: "ok",
    });
  });

  it("sotto il mercato prende il tono negativo", () => {
    const p = conversionStep({
      ...base, converted_signal_date: "2026-09-15",
      outcome_signal_date: "2026-09-15", outcome_horizon_days: 5,
      outcome_mkt_neutral_hit: 0, outcome_mkt_neutral_excess_pct: -0.8,
    });
    expect(p?.esito).toBe("sotto il mercato a 5g (-0,8%)");
    expect(p?.tono).toBe("bad");
  });

  it("un esito senza riferimento dell'universo non e' un insuccesso", () => {
    const p = conversionStep({
      ...base, converted_signal_date: "2026-09-15",
      outcome_signal_date: "2026-09-15", outcome_horizon_days: 21,
      outcome_mkt_neutral_hit: null,
    });
    expect(p?.tono).toBeNull();
    expect(p?.esito).toMatch(/senza riferimento di mercato/);
  });

  it("dice PERCHE' la barra manca, e distingue riconciliato da storico", () => {
    const ric = conversionStep({ ...base, conversion_source: "reconciled" });
    expect(ric).toEqual({
      evento: "barra dell'evento non registrata (riconciliato)",
      esito: "esito non misurabile",
      tono: null,
    });
    const storico = conversionStep({ ...base, conversion_source: "legacy" });
    expect(storico?.evento).toBe("barra dell'evento non registrata (storico)");
    // Uno storico puo' ancora ricevere l'esito del magazzino: non si dichiara perso.
    expect(storico?.esito).toBe("esito in maturazione");
  });

  it("un evento registrato senza esito e' in maturazione", () => {
    expect(conversionStep({ ...base, converted_signal_date: "2026-09-15" })?.esito)
      .toBe("esito in maturazione");
  });
});

describe("conversionBarNote", () => {
  it("tace quando la barra coincide con quella del segnale", () => {
    expect(conversionBarNote("2026-09-15", "2026-09-15")).toBeNull();
    expect(conversionBarNote(null, "2026-09-15")).toBeNull();
  });

  it("parla quando il segnale e' stato aggiornato dopo la conversione", () => {
    expect(conversionBarNote("2026-09-15", "2026-10-08")).toMatch(/barra del 15 set/);
  });
});
