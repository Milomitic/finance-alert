import { expect, it } from "vitest";

import type { LiveQuote } from "@/api/types";

import { moversDeiMiei } from "./moversMiei";

function q(ticker: string, change_pct: number | null, price = 10): LiveQuote {
  return {
    ticker, price, change_pct, prev_close: null, change_abs: null, day_open: null, day_high: null,
    day_low: null, volume: null, market_state: null, currency: null, fetched_at: 0, error: null,
  };
}

const TITOLI = new Map([["A", "preferito"], ["B", "posizione"], ["C", "preferito"], ["D", "preferito"], ["E", "preferito"]]);

it("divide chi sale e chi scende, dal piu' mosso", () => {
  const r = moversDeiMiei(TITOLI, [q("A", 1.2), q("B", -3.4), q("C", 4.1), q("D", -0.5), q("X", 9)], 10);
  expect(r.su.map((m) => m.ticker)).toEqual(["C", "A"]);
  expect(r.giu.map((m) => m.ticker)).toEqual(["B", "D"]);
  expect(r.fuori).toBe(1);   // E senza quotazione; X non e' dei tuoi
});

it("invariati e senza variazione restano fuori, contati", () => {
  const r = moversDeiMiei(TITOLI, [q("A", 0), q("B", null), q("C", Number.NaN)], 10);
  expect([r.su, r.giu, r.fuori]).toEqual([[], [], 5]);
});

it("taglia a `righe` per parte", () => {
  const r = moversDeiMiei(TITOLI, [q("A", 1), q("B", 2), q("C", 3)], 2);
  expect(r.su.map((m) => m.ticker)).toEqual(["C", "B"]);
});
