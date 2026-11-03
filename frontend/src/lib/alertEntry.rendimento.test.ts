import { describe, expect, it } from "vitest";

import { rendimentoDalSegnale } from "./alertEntry";

const alert = (tone: string | undefined, first_price = 100, trigger_price = 120) => ({
  trigger_price,
  snapshot: { tone, first_price },
});

describe("il P/L% di chi avesse seguito il segnale", () => {
  it("rialzista: guadagna se il prezzo sale, misurato dall'INGRESSO e non dal prezzo vivo", () => {
    expect(rendimentoDalSegnale(alert("bull"), 110)).toBeCloseTo(10);
    expect(rendimentoDalSegnale(alert("bull"), 90)).toBeCloseTo(-10);
  });

  it("ribassista: si legge come una posizione corta", () => {
    expect(rendimentoDalSegnale(alert("bear"), 90)).toBeCloseTo(10);
    expect(rendimentoDalSegnale(alert("bear"), 110)).toBeCloseTo(-10);
  });

  it("senza un prezzo attuale niente numero, mai uno zero", () => {
    expect(rendimentoDalSegnale(alert("bull"), null)).toBeNull();
    expect(rendimentoDalSegnale(alert("bull"), 0)).toBeNull();
    expect(rendimentoDalSegnale(alert("bull"), Number.NaN)).toBeNull();
  });
});
