import { describe, expect, it } from "vitest";

import { currencySymbol, displayCurrency, formatMoney, formatMoneySigned } from "./money";

/* 312 of the 1010 catalogued stocks are not quoted in dollars, and the stock
 * detail page hard-coded `$` beside every price. So the defect these tests
 * describe is not "the currency is missing" — it is that a Milan, Hong Kong or
 * London price rendered with a dollar sign.
 *
 * The rule most of this file defends: a currency that cannot be resolved must
 * produce NO symbol, never a default one. `fx_service` reached the same
 * conclusion on the backend, after a version that fell back to 1:1 turned
 * "100 units of anything" into "100 USD" — a missing value wearing the most
 * plausible possible value.
 */

describe("i penny di Londra sono un problema di etichetta, mai di valore", () => {
  it("rietichetta entrambe le grafie di yfinance", () => {
    expect(displayCurrency("GBp")).toBe("GBP");
    expect(displayCurrency("GBX")).toBe("GBP");
  });

  it("non tocca le quotate londinesi gia in sterline", () => {
    expect(displayCurrency("GBP")).toBe("GBP");
  });

  it("non divide il numero", () => {
    // Il difetto speculare, e quello caro. Il valore e stato scalato una volta
    // sola all'ingest; rifarlo qui sarebbe il bug x100 che questo progetto ha
    // gia pagato una volta. Shell chiude a 35.04 STERLINE.
    expect(formatMoney(35.04, "GBp")).toBe("£35.04");
  });

  it("la mappa dello screener sbagliava proprio questo", () => {
    // `CURRENCY_SYMBOL[currency] ?? `${currency} `` su 'GBp' non trovava nulla
    // e rendeva "GBp 35.04": etichetta pence su un numero in sterline.
    expect(formatMoney(35.04, "GBp")).not.toContain("GBp");
  });
});

describe("una valuta assente non diventa il dollaro", () => {
  it("rende il numero nudo quando non c'e valuta", () => {
    // Il caso market asset: un livello di indice non e denominato in niente.
    expect(formatMoney(4521.3, null)).toBe("4521.30");
    expect(formatMoney(4521.3, undefined)).toBe("4521.30");
  });

  it("rifiuta un codice che non ha la forma di una valuta", () => {
    expect(displayCurrency("")).toBeNull();
    expect(displayCurrency("DOLLARI")).toBeNull();
  });

  it("non c'e simbolo da mostrare senza valuta", () => {
    expect(currencySymbol(null)).toBeNull();
  });

  it("la regressione esatta del vecchio helper", () => {
    // /^[A-Z]{3}$/ bocciava 'GBp' per la minuscola e il ternario ripiegava su
    // "USD". Un prezzo in sterline col simbolo del dollaro non e ambiguo, e
    // falso.
    expect(formatMoney(35.04, "GBp")).not.toContain("$");
    expect(formatMoney(4521.3, null)).not.toContain("$");
  });
});

describe("valute diverse restano distinguibili", () => {
  it.each([
    ["USD", "$35.04"],
    ["EUR", "€35.04"],
    ["GBP", "£35.04"],
    ["HKD", "HK$35.04"],
    ["AUD", "A$35.04"],
    ["CAD", "C$35.04"],
  ])("%s rende %s", (code, expected) => {
    expect(formatMoney(35.04, code)).toBe(expected);
  });

  it("i tre dollari non collassano in un simbolo solo", () => {
    // ⚠️ La guardia contro la correzione sbagliata. `Intl` con
    // `currencyDisplay: "narrowSymbol"` rende USD, HKD e AUD tutti "$" — cioe
    // rimette in piedi l'ambiguita che questo modulo esiste per togliere, sui
    // 59 titoli di Hong Kong in catalogo. Se questo test diventa rosso,
    // qualcuno ha sostituito la mappa con quell'opzione.
    const set = new Set([
      currencySymbol("USD"), currencySymbol("HKD"),
      currencySymbol("AUD"), currencySymbol("CAD"),
    ]);
    expect(set.size).toBe(4);
  });

  it("yen e yuan nemmeno", () => {
    // La mappa dello screener aveva '¥' per entrambi. Un prezzo in yuan e uno
    // in yen rendevano identici.
    expect(currencySymbol("JPY")).not.toBe(currencySymbol("CNY"));
  });

  it("una valuta fuori mappa mostra il codice, non un simbolo prestato", () => {
    expect(formatMoney(35.04, "XAU")).toBe("XAU 35.04");
  });
});

describe("i decimali seguono la grandezza", () => {
  it("sopra l'unita bastano due cifre", () => {
    expect(formatMoney(35.041, "USD")).toBe("$35.04");
  });

  it("sotto l'unita ne servono quattro", () => {
    // A due cifre 0.0234 collassa in 0.02 e sparisce la parte che si muove.
    expect(formatMoney(0.0234, "USD")).toBe("$0.0234");
  });

  it("un chiamante puo imporne un numero suo", () => {
    expect(formatMoney(35.0412, "USD", { decimals: 3 })).toBe("$35.041");
  });
});

describe("il segno precede il simbolo", () => {
  it("un guadagno porta il piu", () => {
    expect(formatMoneySigned(12.5, "EUR")).toBe("+€12.50");
  });

  it("una perdita porta un solo meno, davanti al simbolo", () => {
    // "-€12.50", non "€-12.50" e soprattutto non "--€12.50": una colonna di
    // segni si legge scorrendo la prima colonna, e solo se il segno e li.
    expect(formatMoneySigned(-12.5, "EUR")).toBe("-€12.50");
  });

  it("lo zero non e un guadagno", () => {
    expect(formatMoneySigned(0, "EUR")).toBe("€0.00");
  });
});

describe("assenza e zero non condividono un simbolo", () => {
  it.each([null, undefined, NaN, Infinity])("%s rende un trattino", (v) => {
    expect(formatMoney(v as number | null, "USD")).toBe("—");
  });

  it("lo zero e un prezzo, non un'assenza", () => {
    expect(formatMoney(0, "USD")).toBe("$0.00");
  });
});
