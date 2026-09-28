import { describe, expect, it } from "vitest";

import type { CalendarEvent } from "@/api/types";

import { etichettaGiorno, settimana, type Rilevanza } from "./settimana";

/* Che cosa arriva questa settimana (FA-088). */

const LUN = "2026-09-28";

function macro(date: string, label: string, importance: "high" | "medium" | "low", ora = "12:30"): CalendarEvent {
  return { date, kind: "macro", label, importance, region: "US", release_time: ora } as CalendarEvent;
}

function trimestrale(date: string, ticker: string, when: "pre" | "after" | null = null): CalendarEvent {
  return {
    date, kind: "earnings", ticker, name: ticker, eps_estimate: null, revenue_estimate: null,
    sector: null, market_cap: null, earnings_when: when,
  } as CalendarEvent;
}

const SEGUITI = new Map<string, Rilevanza>([["ENI.MI", "preferito"], ["AAPL", "posizione"]]);

describe("la settimana", () => {
  it("sette giorni da oggi, ma un weekend vuoto non occupa colonne", () => {
    const g = settimana([], LUN, SEGUITI);
    expect(g.map((x) => x.giorno)).toEqual([
      "2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02",
    ]);
    expect(g.map((x) => x.distanza)).toEqual([0, 1, 2, 3, 4]);
  });

  it("un weekend con qualcosa resta", () => {
    const g = settimana([macro("2026-10-03", "G20", "high")], LUN, SEGUITI);
    expect(g.map((x) => x.giorno)).toContain("2026-10-03");
  });

  it("solo i macro importanti, e solo le trimestrali dei titoli seguiti", () => {
    const g = settimana([
      macro(LUN, "CPI", "high"), macro(LUN, "Scorte", "medium"),
      trimestrale(LUN, "ENI.MI", "pre"), trimestrale(LUN, "NVDA", "after"),
      trimestrale(LUN, "AAPL", "after"),
    ], LUN, SEGUITI);
    expect(g[0].macro.map((m) => m.etichetta)).toEqual(["CPI"]);
    // Le posizioni prima dei preferiti, come nella lista dei segnali.
    expect(g[0].trimestrali.map((t) => [t.evento.ticker, t.rilevanza])).toEqual([
      ["AAPL", "posizione"], ["ENI.MI", "preferito"],
    ]);
  });

  it("il cambio dell'ora legale americana non salta ne' ripete un giorno", () => {
    // Negli USA l'ora legale finisce domenica 1 novembre 2026.
    const g = settimana([macro("2026-10-31", "x", "high"), macro("2026-11-01", "y", "high")], "2026-10-29", SEGUITI);
    expect(g.map((x) => x.giorno)).toEqual([
      "2026-10-29", "2026-10-30", "2026-10-31", "2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04",
    ]);
  });

  it("senza titoli seguiti restano i macro", () => {
    const g = settimana([macro(LUN, "CPI", "high"), trimestrale(LUN, "AAPL")], LUN, new Map());
    expect(g[0].macro).toHaveLength(1);
    expect(g[0].trimestrali).toHaveLength(0);
  });
});

describe("le etichette", () => {
  it("oggi, domani, poi il giorno col numero", () => {
    expect(etichettaGiorno(LUN, 0)).toBe("Oggi");
    expect(etichettaGiorno("2026-09-29", 1)).toBe("Domani");
    expect(etichettaGiorno("2026-09-30", 2)).toBe("mer 30");
  });
});
