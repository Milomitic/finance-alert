import { describe, expect, it } from "vitest";

import type { CalendarEvent } from "@/api/types";

import { LINEE_AGENDA, giorniAgenda, ripartisciRighe, taglia, vociDelGiorno } from "./agendaGiorni";
import type { Rilevanza } from "./settimana";

const GIO = "2026-10-01"; // giovedi'
const SAB = "2026-10-03";

function macro(date: string, label: string, importance: "high" | "medium" | "low", ora = "12:30"): CalendarEvent {
  return { date, kind: "macro", label, importance, region: "US", release_time: ora } as CalendarEvent;
}

function trimestrale(date: string, ticker: string, cap: number | null = null, when: "pre" | "after" | null = null): CalendarEvent {
  return {
    date, kind: "earnings", ticker, name: ticker, eps_estimate: null, revenue_estimate: null,
    sector: null, market_cap: cap, earnings_when: when,
  } as CalendarEvent;
}

describe("i quattro giorni dell'agenda", () => {
  it("oggi e i tre lavorativi dopo, saltando il fine settimana", () => {
    const g = giorniAgenda([], GIO, new Map());
    expect(g.map((x) => x.giorno)).toEqual(["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06"]);
    expect(g.map((x) => x.distanza)).toEqual([0, 1, 4, 5]);
  });

  it("di sabato si parte dal primo lavorativo", () => {
    const g = giorniAgenda([], SAB, new Map());
    expect(g.map((x) => x.giorno)).toEqual(["2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"]);
    // Il lunedi' non e' «Oggi»: dista due giorni.
    expect(g[0].distanza).toBe(2);
  });

  it("il cambio dell'ora legale americana non salta ne' ripete un giorno", () => {
    // 1 novembre 2026: finisce l'ora legale negli Stati Uniti.
    const g = giorniAgenda([], "2026-10-30", new Map());
    expect(g.map((x) => x.giorno)).toEqual(["2026-10-30", "2026-11-02", "2026-11-03", "2026-11-04"]);
  });

  it("oggi tutti i macro, gli altri giorni solo quelli importanti", () => {
    const g = giorniAgenda([
      macro(GIO, "Sussidi", "high"), macro(GIO, "Scorte", "low"),
      macro("2026-10-02", "Buste paga", "high"), macro("2026-10-02", "Fiducia", "medium"),
    ], GIO, new Map());
    expect(g[0].macro.map((m) => m.etichetta)).toEqual(["Sussidi", "Scorte"]);
    expect(g[1].macro.map((m) => m.etichetta)).toEqual(["Buste paga"]);
  });

  it("tutte le trimestrali, prima le tue e poi per capitalizzazione", () => {
    const seguiti = new Map<string, Rilevanza>([["ENI.MI", "preferito"], ["AAPL", "posizione"]]);
    const g = giorniAgenda([
      trimestrale(GIO, "MSFT", 3e12, "after"), trimestrale(GIO, "ENI.MI", 5e10, "pre"),
      trimestrale(GIO, "XYZ", null), trimestrale(GIO, "AAPL", 3.5e12, "pre"), trimestrale(GIO, "KO", 2e11, "pre"),
    ], GIO, seguiti);
    expect(g[0].trimestrali.map((t) => t.evento.ticker)).toEqual(["AAPL", "ENI.MI", "MSFT", "KO", "XYZ"]);
    expect(g[0].trimestrali.map((t) => t.rilevanza)).toEqual(["posizione", "preferito", null, null, null]);
    expect(vociDelGiorno(g[0])).toBe(5);
  });
});

describe("l'altezza fissa divisa fra le due righe", () => {
  it("in proporzione alle voci del giorno piu' pieno di ogni riga", () => {
    expect(ripartisciRighe([0, 0])).toEqual([5, 5]);
    expect(ripartisciRighe([12, 3])).toEqual([8, 2]);
    expect(ripartisciRighe([1, 40])).toEqual([2, 8]);
    // Il totale e' sempre lo stesso: il riquadro non cambia altezza.
    for (const b of [[0, 9], [3, 3], [100, 1], [7, 2]] as [number, number][]) {
      const [x, y] = ripartisciRighe(b);
      expect(x + y).toBe(LINEE_AGENDA);
      expect(Math.min(x, y)).toBeGreaterThanOrEqual(2);
    }
  });

  it("chi non ci sta lo dice: l'ultima linea e' il «+N altre»", () => {
    expect(taglia(3, 5)).toEqual({ mostrate: 3, altre: 0 });
    expect(taglia(5, 5)).toEqual({ mostrate: 5, altre: 0 });
    expect(taglia(14, 5)).toEqual({ mostrate: 4, altre: 10 });
    expect(taglia(0, 2)).toEqual({ mostrate: 0, altre: 0 });
  });
});
