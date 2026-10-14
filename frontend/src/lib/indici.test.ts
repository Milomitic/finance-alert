import { describe, expect, it } from "vitest";

import { nomeBreveIndice } from "./indici";

describe("il nome breve di un indice", () => {
  it("per nome, non per sigla: NDX non si confonde con la borsa NASDAQ", () => {
    expect(nomeBreveIndice({ code: "NDX", name: "Nasdaq-100" })).toBe("Nasdaq 100");
    expect(nomeBreveIndice({ code: "SP500", name: "S&P 500" })).toBe("S&P 500");
    expect(nomeBreveIndice({ code: "FTSE100", name: "FTSE 100 (London)" })).toBe("FTSE 100");
  });

  it("un indice nuovo prende il nome del catalogo senza la parentesi", () => {
    expect(nomeBreveIndice({ code: "XYZ", name: "Borsa Nuova 40 (Atene)" })).toBe("Borsa Nuova 40");
    expect(nomeBreveIndice({ code: "XYZ", name: "" })).toBe("XYZ");
  });
});
