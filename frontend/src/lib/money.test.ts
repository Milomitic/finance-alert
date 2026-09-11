import { describe, expect, it } from "vitest";

import {
  currencySymbol,
  displayCurrency,
  formatCompactMoney,
  formatMoney,
  formatMoneySigned,
} from "./money";

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

/* ─── La capitalizzazione compatta, nella valuta della riga ───────────────
 *
 * FA-026. `fmtMc` esisteva in DUE copie private identiche — `StockBrowserTable`
 * e `NavbarSearch` — ed entrambe cablavano `$` su una cifra che per 312 titoli
 * su 1010 non e in dollari. E la stessa forma che ha portato `formatMoney` qui:
 * cinque formattatori che stampavano valute diverse per lo stesso prezzo.
 *
 * ⚠️ Misurato in produzione l'11 settembre 2026: la top 10 per capitalizzazione
 * in valuta nativa e quella convertita in dollari NON hanno un titolo in
 * comune. La colonna resta nativa e l'ORDINAMENTO passa per il valore in
 * dollari, lato server — opzione C del piano.
 */
describe("formatCompactMoney", () => {
  it("usa il simbolo della valuta, non il dollaro", () => {
    expect(formatCompactMoney(2_860_000_000_000, "HKD")).toBe("HK$2.86T");
    expect(formatCompactMoney(196_000_000_000, "GBP")).toBe("£196.0B");
    expect(formatCompactMoney(3_000_000_000_000, "USD")).toBe("$3.00T");
  });

  it("⚠️ i quattro dollari restano distinti", () => {
    // Il difetto che `Intl` con `narrowSymbol` reintroduce: USD, HKD e AUD
    // diventano lo stesso `$`, e 59 titoli di Hong Kong leggono dollari USA.
    const v = 1_000_000_000;
    const resi = ["USD", "HKD", "AUD", "CAD"].map((c) => formatCompactMoney(v, c));
    expect(new Set(resi).size).toBe(4);
  });

  it("le pence portano la sterlina, non un'etichetta in pence", () => {
    expect(formatCompactMoney(196_000_000_000, "GBp")).toBe("£196.0B");
  });

  it("le soglie: mille miliardi, miliardi, milioni", () => {
    expect(formatCompactMoney(1.5e12, "USD")).toBe("$1.50T");
    expect(formatCompactMoney(2.4e9, "USD")).toBe("$2.4B");
    expect(formatCompactMoney(7.6e6, "USD")).toBe("$8M");
  });

  it("⚠️ una valuta ignota lascia il numero NUDO, non in dollari", () => {
    // La regola che `fx_service` dichiara nel proprio docstring e che
    // `formatMoney` gia applica: assumere USD perche il campo e vuoto e
    // un'ipotesi presentata come un fatto.
    expect(formatCompactMoney(2.4e9, null)).toBe("2.4B");
    expect(formatCompactMoney(2.4e9, "")).toBe("2.4B");
    expect(formatCompactMoney(2.4e9, "12")).toBe("2.4B");
  });

  it("un codice valido senza simbolo stampa il CODICE, non un numero nudo", () => {
    // ⚠️ Distinzione gia decisa da `currencySymbol`: «HKD 18.40 batte sia
    // "? 18.40" sia un numero nudo». Un codice di tre lettere e etichettabile
    // anche quando non e convertibile — e per questo `market_cap_usd` puo
    // essere null mentre la cifra a schermo resta etichettata.
    expect(formatCompactMoney(2.4e9, "ZZZ")).toBe("ZZZ 2.4B");
  });

  it("assente e un trattino, non zero", () => {
    expect(formatCompactMoney(null, "USD")).toBe("—");
    expect(formatCompactMoney(undefined, "USD")).toBe("—");
  });
});

describe("nessuna schermata rifa la formattazione compatta per conto proprio", () => {
  /* Controllo sulla SORGENTE, come per il Divario e per l'AbortSignal: un test
   * di comportamento non distingue una delega da una seconda copia scritta
   * identica, se non quando hanno gia divergiuto — cioe troppo tardi.
   *
   * ⚠️ La firma cercata e la SOGLIA DEI MILLE MILIARDI con il dollaro davanti,
   * `$${...1e12...}`, che e il formattatore compatto e non un prezzo qualunque.
   * Cercare ogni `$` nel sorgente darebbe decine di risultati e la lista delle
   * esenti diventerebbe piu lunga di quella delle colpevoli — un controllo che
   * nessuno legge piu. */
  const FIRMA_COMPATTA = /\$\$\{[^`]*1e12/;

  /** Esenti, con il motivo. ⚠️ Non e una lista di comodo: ogni voce qui e una
   *  decisione, e una lista che cresce senza motivi e un difetto. */
  const ESENTI: Record<string, string> = {
    "/src/components/stock/StockScoreCard.tsx":
      "Formatta un valore di pilastro ETICHETTATO `usd` dal backend, non una " +
      "capitalizzazione: la valuta e una proprieta della metrica, non della riga. " +
      "Toccarlo qui sarebbe indovinare.",
    "/src/components/dashboard/LiveVolumeMoversCard.tsx":
      "`fmtDollar` formatta il CONTROVALORE, che il backend converte davvero: " +
      "`market_stats_service` calcola `dollar_volume` come " +
      "`vol_today * to_usd(last_close, currency)`. Verificato, non assunto — il " +
      "dollaro li e corretto.",
    "/src/components/stock/MicroDataCard.tsx":
      "`bigUsd` formatta i valori di BILANCIO (enterprise value, ricavi), che " +
      "yfinance serve nella valuta di RENDICONTAZIONE — non dichiarata nel " +
      "payload e non necessariamente quella di quotazione. La capitalizzazione, " +
      "che e l'oggetto di FA-026, delega gia a formatCompactMoney.",
  };

  it("chi stampa una capitalizzazione delega", () => {
    const sorgenti = import.meta.glob("/src/components/**/*.tsx", {
      query: "?raw", import: "default", eager: true,
    }) as Record<string, string>;
    const sospette = Object.entries(sorgenti)
      .filter(([f, t]) => !f.includes(".test.") && FIRMA_COMPATTA.test(t))
      .map(([f]) => f)
      .filter((f) => !(f in ESENTI));
    expect(sospette).toEqual([]);
  });

  it("il censimento vede davvero dei file", () => {
    // Senza, la riga sopra passerebbe su zero sorgenti: vera di niente.
    const sorgenti = import.meta.glob("/src/components/**/*.tsx", {
      query: "?raw", import: "default", eager: true,
    });
    expect(Object.keys(sorgenti).length).toBeGreaterThan(50);
  });
});
