import { describe, expect, it } from "vitest";

import { posizioneSulleFasce, sogliaInFrase } from "./studio";

describe("posizioneSulleFasce (FA-192)", () => {
  const fasce = [{ da: -0.1, a: -0.05 }, { da: -0.05, a: 0 }, { da: 0, a: 0.05 }, { da: 0.05, a: 0.1 }];
  it("interpola dentro la fascia", () => {
    expect(posizioneSulleFasce(0, fasce)).toBe(0.5);
    expect(posizioneSulleFasce(-0.075, fasce)).toBeCloseTo(0.125);
    expect(posizioneSulleFasce(0.1, fasce)).toBe(1);
  });
  it("fuori dall'asse non si disegna", () => {
    expect(posizioneSulleFasce(0.2, fasce)).toBeNull();
    expect(posizioneSulleFasce(null, fasce)).toBeNull();
    expect(posizioneSulleFasce(0, [])).toBeNull();
  });
});

describe("sogliaInFrase (FA-192)", () => {
  it("usa il meno tipografico e la virgola", () => {
    expect(sogliaInFrase(-10)).toBe("−10%");
    expect(sogliaInFrase(7.5)).toBe("+7,5%");
  });
});

describe("domandePronte (FA-199)", () => {
  it("tre domande con l'URL dello Studio, e l'evento giusto per titolo o mercato", async () => {
    const { domandePronte, parametriDaUrl } = await import("./studio");
    const t = domandePronte("AAPL", "titolo");
    expect(t).toHaveLength(3);
    const p = parametriDaUrl(new URLSearchParams(t[0].url.split("?")[1]));
    expect(p).toMatchObject({ simbolo: "AAPL", modello: "dopo_movimento", soglia: -5, sedute: 5, orizzonte: 21 });
    expect(t[2].url).toContain("tipo=trimestrali");
    const m = domandePronte("^GSPC", "mercato");
    expect(parametriDaUrl(new URLSearchParams(m[2].url.split("?")[1]))).toMatchObject({ simbolo: "^GSPC", tipo: "macro", serie: "CPIAUCSL" });
  });
});

describe("urlDaParametri (FA-196/197/198)", () => {
  it("l'URL tiene solo cio' che la domanda usa, e torna uguale", async () => {
    const { parametriDaUrl, urlDaParametri } = await import("./studio");
    for (const q of [
      "simbolo=AAPL&modello=dopo_movimento&sedute=5&soglia=-10&orizzonte=21&netto=%5EGSPC",
      "simbolo=AAPL&modello=primo_passaggio&lato=short&target=8&stop=5&orizzonte=21",
      "simbolo=%5EGSPC&modello=cali&soglia_cali=15",
    ]) {
      const p = parametriDaUrl(new URLSearchParams(q));
      expect(urlDaParametri(p).toString()).toBe(new URLSearchParams(q).toString());
    }
  });

  it("il netto si scrive solo dove la domanda lo accetta", async () => {
    const { parametriDaUrl, urlDaParametri } = await import("./studio");
    const p = parametriDaUrl(new URLSearchParams("simbolo=AAPL&modello=cali&netto=%5EGSPC"));
    expect(urlDaParametri(p).has("netto")).toBe(false);
  });
});
