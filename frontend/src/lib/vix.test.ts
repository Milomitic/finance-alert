import { describe, expect, it } from "vitest";

import {
  bandaVix, intervalloSeduta, movimentoSeduta, movimentoTrentaGiorni, multiploAtteso,
  spiegazioneBande, tonoVariazioneVix,
} from "./vix";

describe("il VIX tradotto in movimento atteso dell'S&P 500", () => {
  it("una seduta vale il VIX diviso la radice di 252", () => {
    // 15,68 -> 0,988%: il numero che la fascia mostra accanto al VIX. Scritto
    // come conto e non come costante, cosi' il test non cambia insieme alla
    // riga che deve sorvegliare.
    expect(movimentoSeduta(15.68)).toBeCloseTo(15.68 / Math.sqrt(252), 6);
    expect(movimentoSeduta(15.68)).toBeCloseTo(0.988, 3);
  });

  it("trenta giorni di CALENDARIO, non di borsa", () => {
    expect(movimentoTrentaGiorni(15.68)).toBeCloseTo(15.68 * Math.sqrt(30 / 365), 6);
    // Controllo negativo: con 30 sedute il numero sarebbe diverso, quindi il
    // test sa distinguere le due convenzioni.
    expect(movimentoTrentaGiorni(15.68)).not.toBeCloseTo(15.68 * Math.sqrt(30 / 252), 2);
  });

  it("l'intervallo sta attorno alla chiusura PRECEDENTE, dove parte la variazione", () => {
    const r = intervalloSeduta(7704, 15.68)!;
    expect(r.basso).toBeCloseTo(7704 * (1 - 0.00988), 0);
    expect(r.alto).toBeCloseTo(7704 * (1 + 0.00988), 0);
  });

  it("senza un VIX o una chiusura validi non inventa un intervallo", () => {
    expect(movimentoSeduta(null)).toBeNull();
    expect(movimentoSeduta(0)).toBeNull();
    expect(intervalloSeduta(null, 15)).toBeNull();
    expect(intervalloSeduta(7700, undefined)).toBeNull();
    expect(multiploAtteso(null, 15)).toBeNull();
  });

  it("il multiplo e' sulla variazione ASSOLUTA: un ribasso non e' un multiplo negativo", () => {
    expect(multiploAtteso(-0.494, 15.68)).toBeCloseTo(0.5, 2);
    expect(multiploAtteso(0.494, 15.68)).toBeCloseTo(0.5, 2);
  });
});

describe("le bande", () => {
  it("seguono le soglie convenzionali, bordo escluso", () => {
    expect(bandaVix(14.99)).toBe("calmo");
    expect(bandaVix(15)).toBe("normale");
    expect(bandaVix(19.99)).toBe("normale");
    expect(bandaVix(20)).toBe("teso");
    expect(bandaVix(30)).toBe("stress");
  });

  it("il suggerimento porta i movimenti CALCOLATI, non una tabella scritta a mano", () => {
    const testo = spiegazioneBande();
    // 20 / radice(252) = 1,26 -> «1,3».
    expect(testo).toContain("15-20 normale (S&P ±0,9-1,3% a seduta)");
    expect(testo).toContain("sotto 15 calmo (S&P entro ±0,9% a seduta)");
    expect(testo).toContain("sopra 30 stress (S&P oltre ±1,9% a seduta)");
  });
});

describe("il colore della variazione e' invertito", () => {
  it("un VIX che sale e' il colore di un mercato che scende", () => {
    expect(tonoVariazioneVix(3.2)).toContain("rose");
    expect(tonoVariazioneVix(-3.2)).toContain("emerald");
  });

  it("una variazione che si arrotonda a zero resta neutra", () => {
    expect(tonoVariazioneVix(0.004)).toBe("text-muted-foreground");
    expect(tonoVariazioneVix(null)).toBe("text-muted-foreground");
  });
});
