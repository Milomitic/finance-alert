import { describe, expect, it } from "vitest";

import { valoreAlla } from "./valoreMedia";

const giorno = (d: string) => Date.parse(d) / 1000;
const punti = [
  { date: "2026-11-02", value: 10 },
  { date: "2026-11-03", value: 11 },
  { date: "2026-11-04", value: null },
];

describe("valoreAlla", () => {
  it("senza mirino, l'ultimo valore non nullo", () => {
    expect(valoreAlla(punti, null, giorno)).toBe(11);
  });
  it("col mirino, il valore di quella barra", () => {
    expect(valoreAlla(punti, giorno("2026-11-02"), giorno)).toBe(10);
  });
  it("una barra senza valore resta senza valore, non prende quello vicino", () => {
    expect(valoreAlla(punti, giorno("2026-11-04"), giorno)).toBeNull();
    expect(valoreAlla(punti, giorno("2026-11-09"), giorno)).toBeNull();
  });
  it("senza serie, niente", () => {
    expect(valoreAlla(undefined, null, giorno)).toBeNull();
  });
});
