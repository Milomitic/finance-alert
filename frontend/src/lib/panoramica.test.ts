import { describe, expect, it } from "vitest";

import { ordinaPer, type RigaUnita, unisciRighe } from "./panoramica";

/* FA-184: l'unione col paniere vivo e l'ordinamento con gli sconosciuti in fondo. */

const r = (symbol: string, ytd: number | null) => ({
  symbol, name: symbol, category: "index", flag: null, ultima_chiusura: 10, data_chiusura: "2026-11-26",
  rendimenti: { ytd }, massimo_52s: null, minimo_52s: null, posizione_52s: null,
  dal_massimo_storico: null, vol_20g: null, vol_1a: null, distanza_ema200: null,
});

describe("panoramica", () => {
  it("gli sconosciuti stanno in fondo in entrambi i versi", () => {
    const righe = unisciRighe([r("A", 0.1), r("B", null), r("C", -0.2)], []) as RigaUnita[];
    expect(ordinaPer(righe, "ytd", true).map((x) => x.symbol)).toEqual(["A", "C", "B"]);
    expect(ordinaPer(righe, "ytd", false).map((x) => x.symbol)).toEqual(["C", "A", "B"]);
  });

  it("prezzo e oggi dal paniere vivo; senza paniere l'ultima chiusura e oggi sconosciuto", () => {
    const vivi = [{ symbol: "A", quote: { price: 12, change_pct: 1.5 }, using_futures: true }] as never;
    const [a, b] = unisciRighe([r("A", 0.1), r("B", 0)], vivi);
    expect(a).toMatchObject({ prezzo: 12, oggi: 0.015, usaFuture: true });
    expect(b).toMatchObject({ prezzo: 10, oggi: null, usaFuture: false });
  });
});
