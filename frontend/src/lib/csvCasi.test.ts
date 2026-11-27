import { describe, expect, it } from "vitest";

import { csvDeiCasi, nomeFileCasi } from "./csvCasi";

/* FA-193: i casi esportati per Excel in italiano. */

const casi = [
  { data: "2025-04-04", esito: 0.0812, episodio: 7, primo: true, mossa: -0.1423 },
  { data: "2025-04-03", esito: Number.NaN, episodio: 7, primo: false, mossa: -0.11 },
];

describe("csvDeiCasi", () => {
  it("BOM, punto e virgola, virgola decimale", () => {
    const csv = csvDeiCasi(casi, true);
    expect(csv.startsWith("﻿")).toBe(true);
    const righe = csv.slice(1).split("\r\n");
    expect(righe[0]).toBe("data;mossa_pct;esito_pct;episodio;primo_giorno_episodio");
    expect(righe[1]).toBe("2025-04-04;-14,23;8,12;7;si");
  });

  it("un esito mancante e' una cella vuota, non NaN", () => {
    expect(csvDeiCasi(casi, true)).toContain("2025-04-03;-11,00;;7;no");
  });

  it("senza la mossa (evento) la colonna non c'e'", () => {
    expect(csvDeiCasi(casi, false).split("\r\n")[0]).toBe("﻿data;esito_pct;episodio;primo_giorno_episodio");
  });

  it("il nome del file non ha caratteri che un disco rifiuta", () => {
    expect(nomeFileCasi("^GSPC", "dopo_movimento")).toBe("studio-_GSPC-dopo_movimento.csv");
  });
});
