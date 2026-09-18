import { describe, expect, it } from "vitest";

import { formatLivello, formatVariazione, posizioneNelRange } from "./marketNumber";

describe("un punto vuol dire una cosa sola", () => {
  it("⚠️ il difetto: migliaia e decimali non possono condividere lo stesso segno", () => {
    /* Erano affiancati nella riga di contesto del cruscotto: «NIKKEI 65.620»
     * accanto ad «ARGENTO 67.63». Il primo punto separava le migliaia, il
     * secondo i decimali. Ora la virgola e' l'unico separatore decimale, e il
     * punto l'unico delle migliaia. */
    expect(formatLivello(65620)).toBe("65.620");
    expect(formatLivello(67.63)).toBe("67,63");
    expect(formatLivello(67.63)).not.toContain(".");
  });

  it("i decimali seguono la SCALA: un indice non ha centesimi, il gas si", () => {
    expect(formatLivello(7730.2)).toBe("7.730");
    expect(formatLivello(2.86)).toBe("2,86");
    expect(formatLivello(0.8412)).toBe("0,8412");
  });

  it("non inventa un valore quando non ce n'e' uno", () => {
    // Uno zero al posto di un dato mancante e' l'affermazione che il mercato
    // e' a zero: la dottrina di `no-value.tsx`, applicata al formattatore.
    expect(formatLivello(null)).toBeNull();
    expect(formatLivello(undefined)).toBeNull();
    expect(formatLivello(Number.NaN)).toBeNull();
    expect(formatLivello(Number.POSITIVE_INFINITY)).toBeNull();
  });
});

describe("formatVariazione", () => {
  it("porta sempre il segno, che il colore non basta", () => {
    expect(formatVariazione(0.21)).toBe("+0,21%");
    expect(formatVariazione(-5.58)).toBe("−5,58%");
  });

  it("⚠️ sotto mezzo centesimo di punto il segno sparisce con la cifra", () => {
    // `-0,004` arrotonda a «0,00»: scriverlo «−0,00%» e' un ribasso che non
    // esiste, ed e' lo stesso difetto di `Math.round(-0.2) === -0` gia'
    // trovato in `earningsProximity`.
    expect(formatVariazione(-0.004)).toBe("0,00%");
    expect(formatVariazione(0)).toBe("0,00%");
    expect(formatVariazione(-0.006)).toBe("−0,01%");
  });

  it("tace quando il dato non c'e'", () => {
    expect(formatVariazione(null)).toBeNull();
    expect(formatVariazione(Number.NaN)).toBeNull();
  });
});

describe("posizioneNelRange", () => {
  it("dice dove sta il prezzo fra minimo e massimo di giornata", () => {
    expect(posizioneNelRange(7730, 7696, 7739)).toBeCloseTo(0.79, 2);
    expect(posizioneNelRange(7696, 7696, 7739)).toBe(0);
    expect(posizioneNelRange(7739, 7696, 7739)).toBe(1);
  });

  it("un prezzo fuori dall'intervallo si ferma al bordo invece di uscire", () => {
    // Il live puo' superare il massimo registrato nell'istantanea: il
    // marcatore resta dentro la barra invece di finire fuori dal riquadro.
    expect(posizioneNelRange(7800, 7696, 7739)).toBe(1);
    expect(posizioneNelRange(7600, 7696, 7739)).toBe(0);
  });

  it("su un intervallo inesistente non dice «a meta'»", () => {
    // Metterlo al centro di un intervallo nullo e' una posizione inventata.
    expect(posizioneNelRange(10, 10, 10)).toBeNull();
    expect(posizioneNelRange(10, 20, 10)).toBeNull();
    expect(posizioneNelRange(10, null, 20)).toBeNull();
  });
});
