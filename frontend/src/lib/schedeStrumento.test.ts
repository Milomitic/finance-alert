import { describe, expect, it } from "vitest";

import { newsDelMercato, schedeDelTitolo } from "./schedeStrumento";

/* Fissa la richiesta del 2026-10-05: niente fondamentali, news e analisti per
 * indici ed ETF su indici; crypto e materie prime perdono fondamentali e
 * analisti ma tengono le news. */
describe("schedeDelTitolo", () => {
  it("un'azione ha tutte le schede", () => {
    expect(schedeDelTitolo("AAPL", "equity")).toEqual({ fondamentali: true, news: true, analisti: true });
  });

  it("senza tipo resta un'azione: una scheda mancante sarebbe peggio di una vuota", () => {
    expect(schedeDelTitolo("AAPL", undefined).fondamentali).toBe(true);
  });

  it("un ETF su indice o settore non ne ha nessuna", () => {
    for (const t of ["SPY", "QQQ", "IWM", "TNA", "XLK", "GDX"]) {
      expect(schedeDelTitolo(t, "etf")).toEqual({ fondamentali: false, news: false, analisti: false });
    }
  });

  it("un ETF su materie prime o crypto tiene solo le news", () => {
    for (const t of ["USO", "gld", "IBIT"]) {
      expect(schedeDelTitolo(t, "etf")).toEqual({ fondamentali: false, news: true, analisti: false });
    }
  });
});

describe("newsDelMercato", () => {
  it("crypto e materie prime si, indici no", () => {
    expect(newsDelMercato("crypto")).toBe(true);
    expect(newsDelMercato("commodity")).toBe(true);
    expect(newsDelMercato("index")).toBe(false);
  });
});
