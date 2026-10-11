import { describe, expect, it } from "vitest";

import { eUnaVariazione, formatConsenso } from "./consensoMacro";

describe("i valori del consenso macro", () => {
  it("una variazione porta il segno, senza zeri inutili", () => {
    expect(formatConsenso(0.4, "%", true)).toBe("+0.4%");
    expect(formatConsenso(0.396, "%", true)).toBe("+0.4%");
    expect(formatConsenso(-0.1, "%", true)).toBe("-0.1%");
    // Una variazione percentuale a una cifra decimale: il precedente ricavato da FRED.
    expect(formatConsenso(0.07, "%", true)).toBe("+0.1%");
    expect(formatConsenso(-0.46, "%", true)).toBe("-0.5%");
    // Una sorpresa in punti resta a due: 0,25 non e' 0,3.
    expect(formatConsenso(0.25, "", true)).toBe("+0.25");
  });

  it("un tasso no: «+3.75%» direbbe che e' salito di tanto", () => {
    expect(formatConsenso(3.75, "%", false)).toBe("3.75%");
  });

  it("un conteggio resta nella sua scala", () => {
    expect(formatConsenso(212, "K", false)).toBe("212K");
    expect(formatConsenso(null, "K", false)).toBe("—");
  });

  it("e' una variazione se il consenso e' in % e la serie non e' un tasso", () => {
    expect(eUnaVariazione("index", "%")).toBe(true);
    expect(eUnaVariazione("level", "%")).toBe(true);
    expect(eUnaVariazione("pct", "%")).toBe(false);
    expect(eUnaVariazione("index", "K")).toBe(false);
  });
});
