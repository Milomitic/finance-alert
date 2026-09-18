import { describe, expect, it } from "vitest";

import { entryPrice, priceHasMoved } from "./alertEntry";

/* Il caso FICO, coi numeri veri presi dalla produzione. */
const fico = {
  trigger_price: 985.39,                    // la chiusura dell'11 settembre
  snapshot: { first_price: 932.26 },        // quella del 4, quando l'alert è comparso
};

describe("il prezzo d'ingresso di un alert", () => {
  it("è quello della prima emissione, non dell'ultima revisione", () => {
    expect(entryPrice(fico)).toBe(932.26);
  });

  it("senza il campo ripiega sul prezzo dell'alert", () => {
    // Gli alert che precedono il campo: è il meglio disponibile.
    expect(entryPrice({ trigger_price: 985.39 })).toBe(985.39);
    expect(entryPrice({ trigger_price: 985.39, snapshot: {} })).toBe(985.39);
  });

  it("uno snapshot malformato non fa esplodere niente", () => {
    for (const first_price of [null, "932.26", 0, -5, Number.NaN]) {
      expect(entryPrice({ trigger_price: 985.39, snapshot: { first_price } })).toBe(985.39);
    }
  });

  it("riconosce quando il prezzo del segnale vivo si è mosso", () => {
    expect(priceHasMoved(fico)).toBe(true);
    // 985.39 contro 932.26 è il 5,7%: ben oltre la soglia dello 0,5%.
  });

  it("non segnala un movimento quando i due coincidono", () => {
    expect(priceHasMoved({ trigger_price: 100, snapshot: { first_price: 100 } })).toBe(false);
    // ⚠️ E nemmeno sul ripiego: senza il campo i due numeri SONO lo stesso, e
    // mostrarli come due direbbe che si sono mossi quando non lo sappiamo.
    expect(priceHasMoved({ trigger_price: 100 })).toBe(false);
  });
});
