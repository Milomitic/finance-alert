import { describe, expect, it } from "vitest";

import { comprimeGiornate, filtersFromSearch, searchFromState } from "@/lib/alertFilters";
import { filtriDellaGiornata, giornoDelTesto } from "@/lib/giornateDiMercato";

/* FA-152: sull'universo le giornate di mercato escono dalla lista. */

const f = (q: string) => filtersFromSearch(new URLSearchParams(q));

describe("giornate di mercato", () => {
  it("si comprime sull'universo, non sui miei titoli", () => {
    expect(comprimeGiornate(f("titoli=tutti"))).toBe(true);
    expect(comprimeGiornate(f("titoli=etoro"))).toBe(true);
    expect(comprimeGiornate(f(""))).toBe(false);          // default: i miei titoli
  });

  it("un filtro di data apre la giornata, e la scelta esplicita le mostra tutte", () => {
    expect(comprimeGiornate(f("titoli=tutti&date_from=2026-11-05"))).toBe(false);
    expect(comprimeGiornate(f("titoli=tutti&giornate=tutte"))).toBe(false);
  });

  it("passare da miei a tutti la accende senza altro", () => {
    const miei = f("");
    expect(comprimeGiornate({ ...miei, solo_rilevanti: undefined })).toBe(true);
  });

  it("nell'URL resta solo la scelta di mostrarle", () => {
    const tutti = f("titoli=tutti");
    expect(searchFromState(tutti, 0, "rilevanza", "desc", new URLSearchParams()).get("giornate")).toBeNull();
    const mostra = searchFromState({ ...tutti, mostra_giornate: true }, 0, "rilevanza", "desc",
      new URLSearchParams());
    expect(mostra.get("giornate")).toBe("tutte");
    expect(comprimeGiornate(filtersFromSearch(mostra))).toBe(false);
  });

  it("aprire una giornata filtra quel giorno e quel verso", () => {
    const g = { giorno: "2026-11-05", tono: "bear", segnali: 104, soglia: 74 };
    const out = filtriDellaGiornata(f("titoli=tutti"), g);
    expect([out.date_from, out.date_to, out.tone]).toEqual(["2026-11-05", "2026-11-05", "bear"]);
    expect(comprimeGiornate(out)).toBe(false);
  });

  it("la data si legge dal testo, non dal fuso", () => {
    expect(giornoDelTesto("2026-11-05")).toBe("5 nov");
    expect(giornoDelTesto("2026-01-31")).toBe("31 gen");
  });
});
