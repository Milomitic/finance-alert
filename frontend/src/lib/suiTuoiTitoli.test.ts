import { describe, expect, it } from "vitest";

import { quandoTrimestrale, tempoFa } from "./suiTuoiTitoli";

const t = (data: string, giorni: number, ora_utc: string | null = null) =>
  ({ ticker: "X", rilevanza: "posizione", data, giorni, ora_utc });

describe("formati della scheda Sui tuoi titoli", () => {
  it("la data viene dal testo, l'ora e' di Roma", () => {
    expect(quandoTrimestrale(t("2026-11-20", 0))).toBe("oggi");
    expect(quandoTrimestrale(t("2026-11-21", 1))).toBe("domani");
    expect(quandoTrimestrale(t("2026-11-20", 5))).toBe("ven 20 nov");
    expect(quandoTrimestrale(t("2026-11-21", 5, "21:00"))).toBe("sab 21 nov 22:00");
  });

  it("il tempo trascorso", () => {
    const adesso = Date.parse("2026-11-16T12:00:00Z");
    expect(tempoFa("2026-11-16T11:48:00Z", adesso)).toBe("12 min fa");
    expect(tempoFa("2026-11-16T09:00:00Z", adesso)).toBe("3 h fa");
    expect(tempoFa("2026-11-14T12:00:00Z", adesso)).toBe("2 g fa");
    expect(tempoFa("ieri", adesso)).toBe("");
  });
});
