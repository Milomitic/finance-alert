import { describe, expect, it } from "vitest";

import type { EtoroAndamento, EtoroVivo } from "@/api/etoro";

import { periodoDi, piuVicino, serieDi, tracciato, verso } from "./patrimonio";

const ADESSO = Date.parse("2026-10-06T10:00:00Z");

const VIVO = { valore: 8255.93, valore_ieri: 8713.89 } as EtoroVivo;

const ANDAMENTO: EtoroAndamento = {
  configurato: true,
  giorni: [
    { giorno: "2026-08-01", valore: 7000, pnl_aperto: 0, fonte: "storico" },
    { giorno: "2026-09-29", valore: 8000, pnl_aperto: 100, fonte: "storico" },
    { giorno: "2026-10-05", valore: 8713.89, pnl_aperto: 900, fonte: "storico" },
    { giorno: "2026-10-06", valore: 8300, pnl_aperto: 700, fonte: "vivo" },
  ],
  oggi: [
    { istante: "2026-10-06T08:00:00Z", valore: 8600 },
    { istante: "2026-10-06T07:00:00Z", valore: 8700 },
  ],
  periodi: [{ chiave: "1M", dal: "2026-09-05", valore_iniziale: 7900, valore_finale: 8255.93, variazione: 355.93,
    generato: 300, realizzato: 50, flussi: 55.93, generato_pct: 3.8 }],
};

describe("serieDi", () => {
  it("oggi: i punti in ordine, il vivo in fondo, la chiusura di ieri come base", () => {
    const s = serieDi("oggi", ANDAMENTO, VIVO, ADESSO);
    expect(s.punti.map((p) => p.v)).toEqual([8700, 8600, 8255.93]);
    expect(s.base).toBe(8713.89);
  });

  it("un intervallo di giorni sostituisce la riga di oggi col vivo e taglia il resto", () => {
    const s = serieDi("1S", ANDAMENTO, VIVO, ADESSO);
    expect(s.punti.map((p) => p.v)).toEqual([8000, 8713.89, 8255.93]);
    expect(s.base).toBe(8000);
  });

  it("fra mezzanotte e le 2 di Roma non scarta la chiusura di ieri", () => {
    // 22:50 UTC del 5 = 00:50 del 6 a Roma: la riga viva e' quella del 6.
    const notte = Date.parse("2026-10-05T22:50:00Z");
    const s = serieDi("1S", ANDAMENTO, VIVO, notte);
    expect(s.punti.map((p) => p.v)).toEqual([8000, 8713.89, 8255.93]);
  });

  it("senza vivo resta lo storico com'e'", () => {
    const s = serieDi("1M", ANDAMENTO, undefined, ADESSO);
    expect(s.punti.map((p) => p.v)).toEqual([8000, 8713.89, 8300]);
  });

  it("senza dati, una serie vuota", () => {
    expect(serieDi("1A", undefined, undefined, ADESSO)).toEqual({ punti: [], base: null });
    expect(serieDi("oggi", undefined, undefined, ADESSO)).toEqual({ punti: [], base: null });
  });
});

describe("tracciato", () => {
  it("riempie il riquadro e la base sta dentro la scala", () => {
    const t = tracciato(serieDi("oggi", ANDAMENTO, VIVO, ADESSO), 300, 100)!;
    expect(t.xy[0].x).toBe(0);
    expect(t.xy[t.xy.length - 1].x).toBe(300);
    // La base (8713,89) e' il massimo: sta in alto, al margine.
    expect(t.yBase).toBeCloseTo(6);
    expect(t.area.endsWith("Z")).toBe(true);
  });

  it("sotto i due punti non c'e' andamento", () => {
    expect(tracciato({ punti: [{ t: 1, v: 1 }], base: null }, 100, 50)).toBeNull();
  });

  it("una serie piatta non divide per zero", () => {
    const t = tracciato({ punti: [{ t: 1, v: 5 }, { t: 2, v: 5 }], base: 5 }, 100, 50)!;
    expect(t.xy.every((q) => Number.isFinite(q.y))).toBe(true);
  });

  it("il cursore prende il punto piu' vicino", () => {
    const t = tracciato(serieDi("oggi", ANDAMENTO, VIVO, ADESSO), 300, 100)!;
    expect(piuVicino(t, 299).p.v).toBe(8255.93);
    expect(piuVicino(t, 1).p.v).toBe(8700);
  });
});

describe("periodi e verso", () => {
  it("il periodo del server per l'intervallo, nessuno per oggi", () => {
    expect(periodoDi("1M", ANDAMENTO)?.generato).toBe(300);
    expect(periodoDi("oggi", ANDAMENTO)).toBeNull();
    expect(periodoDi("3M", ANDAMENTO)).toBeNull();
  });

  it("il verso rispetto alla base", () => {
    expect(verso(serieDi("oggi", ANDAMENTO, VIVO, ADESSO))).toBe("giu");
    expect(verso(serieDi("1S", ANDAMENTO, VIVO, ADESSO))).toBe("su");
    expect(verso({ punti: [], base: null })).toBe("piatto");
  });
});
