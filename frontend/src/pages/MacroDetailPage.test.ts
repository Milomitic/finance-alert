import { describe, expect, it } from "vitest";

import { formatMacroValue } from "./MacroDetailPage";

/* La scala della serie contro il suffisso compatto.
 *
 * Il difetto: la scheda dell'indicatore rende, testualmente,
 * `Total Non-Farm Payrolls (thousands)` e il formatter stampava `159.1K` sul
 * valore memorizzato 159100. Il numero e gia in migliaia, quindi vale 159,1
 * MILIONI di occupati: il suffisso ne aggiungeva altre tre cifre e sbagliava
 * di mille volte. **L'unita era nel payload e il formatter la ignorava.**
 *
 * Il difetto pericoloso non e il caso assurdo. Su una serie in unita semplici
 * il vecchio comportamento era corretto, quindi il bug si vedeva solo dove la
 * scala esisteva — cioe da nessuna parte, finche' qualcuno non ha letto la
 * didascalia accanto al numero.
 */

describe("il suffisso compatto consuma la scala della serie", () => {
  it("una serie in migliaia non prende una seconda K", () => {
    const rendered = formatMacroValue(159_100, "level", "thousands");

    expect(rendered).toBe("159.1M");
    expect(rendered).not.toContain("K");
  });

  it("una serie in miliardi resta nell'ordine di grandezza giusto", () => {
    // PIL reale statunitense: ~23.000 miliardi memorizzati come 23000.
    expect(formatMacroValue(23_000, "level", "billions")).toBe("23.00T");
  });

  it("una serie in milioni pure", () => {
    // Vendite al dettaglio: ~700.000 milioni al mese.
    expect(formatMacroValue(700_000, "level", "millions")).toBe("700.00B");
  });

  it("una serie in unita semplici si comporta come prima", () => {
    // Il controllo negativo: senza di esso, un formatter che moltiplica
    // sempre passerebbe tutti i test sopra.
    expect(formatMacroValue(159_100, "level", "ones")).toBe("159.1K");
  });
});

describe("una scala ignota non viene indovinata", () => {
  it("mostra il numero memorizzato senza applicare alcuna trasformazione", () => {
    // Un suffisso qui sarebbe un'affermazione su una grandezza che non
    // sappiamo risolvere. Il numero pero e comunque vero, quindi si mostra
    // invece di nasconderlo — la stessa scelta che `lib/money.ts` fa quando
    // manca la valuta.
    expect(formatMacroValue(159_100, "level", null)).toBe("159.100");
  });

  it("nemmeno quando la scala e una stringa che non conosciamo", () => {
    expect(formatMacroValue(159_100, "level", "quintali")).toBe("159.100");
  });

  it("e non inventa un suffisso neppure per un valore grande", () => {
    const rendered = formatMacroValue(23_000_000_000_000, "level", undefined);

    expect(rendered).not.toMatch(/[KMBT]$/);
  });
});

describe("gli altri tipi di valore non sono toccati dalla scala", () => {
  it("una percentuale resta una percentuale", () => {
    expect(formatMacroValue(4.25, "pct", "thousands")).toBe("4.25%");
  });

  it("un rendimento pure", () => {
    expect(formatMacroValue(4.25, "yield", "billions")).toBe("4.25%");
  });

  it("un indice pure", () => {
    expect(formatMacroValue(315.42, "index", "millions")).toBe("315.4");
  });
});

describe("assenza e zero non condividono un simbolo", () => {
  it.each([NaN, Infinity, -Infinity])("%s rende un trattino", (v) => {
    expect(formatMacroValue(v, "level", "thousands")).toBe("—");
  });

  it("lo zero e un valore, non un'assenza", () => {
    expect(formatMacroValue(0, "level", "thousands")).toBe("0");
  });
});
