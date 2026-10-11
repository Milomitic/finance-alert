import { describe, expect, it } from "vitest";

import type { TickerHolder } from "@/api/types";

import { ordina, riepilogo, variazione } from "./fondiDetentori";

function fondo(id: number, nome: string, extra: Partial<TickerHolder> = {}): TickerHolder {
  return {
    institutional_id: id, institutional_slug: nome.toLowerCase().replace(/\W+/g, "-"), institutional_name: nome,
    institutional_manager: null, institutional_type: "superinvestor", period_end_date: "2026-06-30",
    shares: 100, value_usd: 1e6, portfolio_pct: 1, shares_change_pct: null, portfolio_weight_delta_pp: null,
    action: "hold", ...extra,
  } as TickerHolder;
}

const FONDI = [
  fondo(1, "Dorsey Asset", { portfolio_pct: 8.5, value_usd: 132.16e6, action: "add", portfolio_weight_delta_pp: 3 }),
  fondo(2, "Dodge & Cox", { portfolio_pct: 2.4, value_usd: 4.55e9, action: "add", portfolio_weight_delta_pp: 0.1 }),
  fondo(3, "AQR Capital", { portfolio_pct: 0.3, value_usd: 909.11e6, action: "reduce", portfolio_weight_delta_pp: -0.3 }),
  fondo(4, "Nuovo Fondo", { portfolio_pct: null, value_usd: null, action: "new", period_end_date: "2026-03-31" }),
];

describe("i fondi che detengono un titolo", () => {
  it("il riepilogo somma le posizioni intere, non i movimenti", () => {
    const r = riepilogo(FONDI);
    expect(r.fondi).toBe(4);
    expect(r.valoreTotale).toBeCloseTo(132.16e6 + 4.55e9 + 909.11e6, 0);
    expect([r.aumentano, r.riducono, r.nuovi]).toEqual([2, 1, 1]);
    // La data piu' frequente, non l'ultima della lista.
    expect(r.periodo).toBe("2026-06-30");
    expect(riepilogo([]).valoreTotale).toBeNull();
  });

  it("per peso o per valore, i dati mancanti in fondo", () => {
    expect(ordina(FONDI, "peso").map((h) => h.institutional_id)).toEqual([1, 2, 3, 4]);
    expect(ordina(FONDI, "valore").map((h) => h.institutional_id)).toEqual([2, 3, 1, 4]);
  });

  it("il movimento: nuovo, punti di peso, poi azioni", () => {
    expect(variazione(FONDI[0])).toMatchObject({ testo: "+3.0 pp", tono: "su" });
    expect(variazione(FONDI[2])).toMatchObject({ testo: "−0.3 pp", tono: "giu" });
    expect(variazione(FONDI[3])).toMatchObject({ testo: "nuovo", tono: "su" });
    expect(variazione(fondo(5, "A", { portfolio_weight_delta_pp: 0.02 }))).toMatchObject({ testo: "=", tono: "fermo" });
    expect(variazione(fondo(6, "B", { shares_change_pct: -12.4, action: "reduce" })))
      .toMatchObject({ testo: "−12% az.", tono: "giu" });
    expect(variazione(fondo(7, "C", { action: null }))).toBeNull();
  });
});
