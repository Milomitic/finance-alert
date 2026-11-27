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
