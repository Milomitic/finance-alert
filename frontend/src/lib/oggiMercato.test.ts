import { describe, expect, it } from "vitest";

import type { CalendarEvent } from "@/api/types";

import { agendaDelGiorno, agendaVuota, oraNewYork } from "./oggiMercato";

function macro(date: string, label: string, release_time: string | null, extra = {}): CalendarEvent {
  return {
    kind: "macro", date, label, importance: "high", region: "US",
    release_time, series_id: 1, ...extra,
  } as CalendarEvent;
}

function trimestrale(
  date: string, ticker: string, when: "pre" | "after" | null, market_cap: number | null = 1e9,
): CalendarEvent {
  return {
    kind: "earnings", date, ticker, name: ticker, eps_estimate: null,
    revenue_estimate: null, sector: null, market_cap, earnings_when: when,
  } as CalendarEvent;
}

describe("oraNewYork", () => {
  it("converte l'orario UTC del rilascio nell'ora della borsa", () => {
    // 12:30 UTC e' l'orario canonico del dato macro americano: 08:30 a New
    // York, un'ora prima dell'apertura.
    expect(oraNewYork("2026-09-18", "12:30")).toBe("08:30");
  });

  it("⚠️ segue l'ora legale invece di sottrarre uno scostamento fisso", () => {
    // Lo STESSO 08:30 di New York e' 12:30 UTC d'estate e 13:30 d'inverno. Chi
    // cablasse -4 o -5 sbaglierebbe meta' anno, e in silenzio.
    expect(oraNewYork("2026-01-15", "13:30")).toBe("08:30");
    expect(oraNewYork("2026-01-15", "12:30")).toBe("07:30");
  });

  it("senza un orario pubblicato non ne inventa uno", () => {
    // Parecchie serie FRED non hanno l'ora: «00:00» sarebbe una scaletta falsa.
    expect(oraNewYork("2026-09-18", null)).toBeNull();
    expect(oraNewYork("2026-09-18", "mattina")).toBeNull();
    expect(oraNewYork("non-una-data", "12:30")).toBeNull();
  });
});

describe("agendaDelGiorno", () => {
  const OGGI = "2026-09-18";
  const eventi: CalendarEvent[] = [
    macro(OGGI, "Richieste sussidi", "12:30"),
    macro(OGGI, "Fiducia consumatori", "14:00"),
    macro(OGGI, "Indice senza orario", null, { importance: "medium" }),
    macro(OGGI, "Altro senza orario", null, { importance: "high" }),
    macro("2026-09-17", "CPI di ieri", "12:30"),
    trimestrale(OGGI, "AAPL", "pre", 3e12),
    trimestrale(OGGI, "GLW", "pre", 4e10),
    trimestrale(OGGI, "NVDA", "after", 2e12),
    trimestrale(OGGI, "PURR", null, null),
    trimestrale("2026-09-19", "MSFT", "pre", 3e12),
  ];

  it("tiene solo il giorno chiesto — quello di New York", () => {
    const a = agendaDelGiorno(eventi, OGGI);
    expect(a.macro.map((m) => m.etichetta)).not.toContain("CPI di ieri");
    expect([...a.primaDellApertura, ...a.dopoLaChiusura].map((e) => e.ticker))
      .not.toContain("MSFT");
  });

  it("i macro si leggono come una scaletta, per orario", () => {
    const a = agendaDelGiorno(eventi, OGGI);
    expect(a.macro.map((m) => m.oraET)).toEqual(["08:30", "10:00", null, null]);
    // Fra due voci senza orario decide l'importanza, non l'ordine d'arrivo.
    expect(a.macro[2].etichetta).toBe("Altro senza orario");
  });

  it("le trimestrali si dividono per momento della seduta, le piu' grosse prime", () => {
    const a = agendaDelGiorno(eventi, OGGI);
    expect(a.primaDellApertura.map((e) => e.ticker)).toEqual(["AAPL", "GLW"]);
    expect(a.dopoLaChiusura.map((e) => e.ticker)).toEqual(["NVDA"]);
    // ⚠️ Chi non dichiara il momento NON viene attribuito d'ufficio al
    // mattino: `earnings_when` e' gia' un'inferenza sull'orario di yfinance,
    // e inferire sopra un'inferenza e' come si costruisce un numero falso.
    expect(a.senzaOrario.map((e) => e.ticker)).toEqual(["PURR"]);
  });

  it("una capitalizzazione ignota va in fondo, non in testa", () => {
    // Trattarla come zero la metterebbe ultima; trattarla come mancante e
    // ordinarla per caso la metterebbe ovunque. Qui sta in fondo per scelta.
    const a = agendaDelGiorno(
      [trimestrale(OGGI, "IGNOTA", "pre", null), trimestrale(OGGI, "PICCOLA", "pre", 1e8)],
      OGGI,
    );
    expect(a.primaDellApertura.map((e) => e.ticker)).toEqual(["PICCOLA", "IGNOTA"]);
  });

  it("regge un calendario assente senza esplodere", () => {
    expect(agendaVuota(agendaDelGiorno(undefined, OGGI))).toBe(true);
    expect(agendaVuota(agendaDelGiorno([], OGGI))).toBe(true);
  });

  it("⚠️ controllo negativo: con eventi veri NON e' vuota", () => {
    // Senza questo, `agendaVuota` sarebbe vera anche di una funzione che
    // scarta tutto, e la riga «oggi» non comparirebbe mai.
    expect(agendaVuota(agendaDelGiorno(eventi, OGGI))).toBe(false);
  });
});
