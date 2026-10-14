import { describe, expect, it } from "vitest";

import type { FundamentalsAnnual } from "@/api/types";

import { completezzaFondamentali } from "./confidenza";

const anno = (y: number, extra: Partial<FundamentalsAnnual> = {}): FundamentalsAnnual => ({
  fiscal_year_end: `${y}-12-31`, revenue: 1, net_income: 1, eps: 1, ...extra,
});
const OGGI = "2026-10-14";

describe("la completezza dei fondamentali", () => {
  it("un semestrale con quattro anni completi e' al 100%: le trimestrali che non pubblica non mancano", () => {
    const r = completezzaFondamentali({ annual: [anno(2025), anno(2024), anno(2023), anno(2022)], quarterly: [], earnings: [] }, OGGI);
    expect(r).toEqual({ valore: 100, presenti: 12, attesi: 12 });
  });

  it("ricavi e utile assenti negli ultimi due anni: il caso 0016.HK", () => {
    const r = completezzaFondamentali({
      annual: [anno(2026, { revenue: null, net_income: null }), anno(2025, { revenue: null, net_income: null }), anno(2024), anno(2023)],
      quarterly: [], earnings: [],
    }, OGGI);
    expect(r?.valore).toBe(67);
  });

  it("un anno che manca pesa come tre valori assenti", () => {
    const r = completezzaFondamentali({ annual: [anno(2025), anno(2024), anno(2023)], quarterly: [], earnings: [] }, OGGI);
    expect(r).toEqual({ valore: 75, presenti: 9, attesi: 12 });
  });

  it("dei risultati contano solo quelli passati", () => {
    const r = completezzaFondamentali({
      annual: [anno(2025), anno(2024), anno(2023), anno(2022)],
      quarterly: [{ fiscal_quarter_end: "2026-06-30", revenue: 1, eps: 1 }],
      earnings: [
        { date: "2026-07-30", eps_estimate: 1, eps_reported: null, surprise_pct: null },
        { date: "2026-10-29", eps_estimate: 1, eps_reported: null, surprise_pct: null }, // futura
      ],
    }, OGGI);
    expect(r).toEqual({ valore: 94, presenti: 15, attesi: 16 });
  });

  it("niente bilancio, niente misura", () => {
    expect(completezzaFondamentali({ annual: [], quarterly: [], earnings: [] }, OGGI)).toBeNull();
  });
});
