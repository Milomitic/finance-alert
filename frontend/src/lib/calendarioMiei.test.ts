import { expect, it } from "vitest";

import type { CalendarEvent } from "@/api/types";

import { soloDeiMieiTitoli } from "./calendarioMiei";

const EVENTI = [
  { kind: "earnings", ticker: "MB.MI", date: "2026-11-05" },
  { kind: "earnings", ticker: "AAPL", date: "2026-10-29" },
  { kind: "macro", date: "2026-10-02", importance: "high" },
] as unknown as CalendarEvent[];

it("tiene le trimestrali dei tuoi titoli e tutti i macro", () => {
  const out = soloDeiMieiTitoli(EVENTI, new Map([["MB.MI", "posizione"]]));
  expect(out.map((e) => (e.kind === "earnings" ? e.ticker : e.kind))).toEqual(["MB.MI", "macro"]);
});

it("senza titoli seguiti restano solo i macro", () => {
  expect(soloDeiMieiTitoli(EVENTI, new Map()).map((e) => e.kind)).toEqual(["macro"]);
});
