import { describe, expect, it } from "vitest";

import { nomeCategoria, prezzoMercato } from "./prezzoMercato";

/* FA-183: il prezzo di un mercato all'italiano, senza perdere i decimali. */

describe("prezzoMercato", () => {
  it.each([
    [7297.49, "index", "7.297,49"],
    [47.59, "commodity", "47,59"],
    [63570.89, "crypto", "63.571"],
    [1775.38, "crypto", "1.775,38"],
    [0.006812, "fx", "0,0068"],
    [-1.5, "index", "−1,50"],
    [1.093612, "fx", "1,0936"],
    [104.053, "fx", "104,05"],
  ])("%s (%s) → %s", (v, c, atteso) => {
    expect(prezzoMercato(v, c)).toBe(atteso);
  });

  it("un valore assente e' un trattino, non uno zero", () => {
    expect(prezzoMercato(null, "index")).toBe("—");
    expect(prezzoMercato(Number.NaN, "index")).toBe("—");
  });

  it("le categorie si dicono in italiano", () => {
    expect(nomeCategoria("index")).toBe("Indice");
    expect(nomeCategoria("commodity")).toBe("Materia prima");
  });
});
