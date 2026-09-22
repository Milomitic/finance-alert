import { describe, expect, it } from "vitest";

import type { Mover } from "@/api/types";

import { completaMover, daLiveMover } from "./liveMovers";

/* Le righe del «Top movers» che arrivano dal giro live: prima portavano solo
 * prezzo e variazione, e le ultime due colonne — volume e punteggio — erano
 * «—» proprio per i titoli che si muovevano di piu' oggi (2026-09-22). */

describe("daLiveMover", () => {
  it("porta volume, moltiplicatore, punteggio, borsa e l'istante della lettura", () => {
    const m = daLiveMover({
      ticker: "WBD", name: "Warner Bros. Discovery", change_pct: 10.79, price: 30.8,
      vol_today: 2_500_000, vol_ratio: 2.5, composite: 72.5, exchange: "NASDAQ",
      as_of: "2026-09-22T15:30:00Z",
    });
    expect(m.vol_today).toBe(2_500_000);
    expect(m.vol_ratio).toBe(2.5);
    expect(m.composite).toBe(72.5);
    expect(m.exchange).toBe("NASDAQ");
    expect(m.vol_as_of).toBe("2026-09-22T15:30:00Z");
    expect(m.last_close).toBe(30.8);
  });

  it("una risposta di un backend precedente resta leggibile: campi nulli, non assenti", () => {
    const m = daLiveMover({ ticker: "AAA", name: null, change_pct: 3, price: null });
    expect(m.name).toBe("AAA");
    expect(m.vol_today).toBeNull();
    expect(m.composite).toBeNull();
  });
});

describe("completaMover", () => {
  const live: Mover = daLiveMover({ ticker: "SHOP", name: "Shopify", change_pct: 7.88, price: 148.79 });
  const eod: Mover = {
    ticker: "SHOP", name: "Shopify Inc.", index: "NDX", sector: "Technology",
    change_pct: -1.2, last_close: 138, prev_close: 139.7,
    vol_today: 9_000_000, vol_ratio: 1.1, composite: 64, exchange: "NASDAQ",
  };

  it("la seconda copia riempie cio' che manca alla prima", () => {
    const m = completaMover(live, eod);
    expect(m.composite).toBe(64);
    expect(m.sector).toBe("Technology");
    expect(m.vol_today).toBe(9_000_000);
  });

  it("⚠️ ma non riporta indietro cio' che la prima ha: variazione e prezzo live restano", () => {
    const m = completaMover(live, eod);
    expect(m.change_pct).toBe(7.88);
    expect(m.last_close).toBe(148.79);
    expect(m.name).toBe("Shopify");
  });

  it("non tocca gli argomenti", () => {
    completaMover(live, eod);
    expect(live.composite).toBeNull();
  });
});
