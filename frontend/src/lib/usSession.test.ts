import { afterEach, describe, expect, it } from "vitest";

import {
  AFTER_CLOSE_MIN, RTH_CLOSE_MIN, RTH_OPEN_MIN,
  etWallClock, formatDelta, usSessionClock,
} from "./usSession";

/* Gli istanti sono scritti in UTC perche' `Date.parse` di una stringa con la
 * Z non dipende dalla macchina: cosi' l'ATTESA e' l'ora di New York e il
 * confronto e' fra due cose diverse. Scriverli in ora locale renderebbe il
 * test vero per costruzione sul portatile di chi lo scrive. */
const VEN_0930_ET = new Date("2026-09-18T13:30:00Z"); // venerdi', apertura
const VEN_0929_ET = new Date("2026-09-18T13:29:00Z");
const VEN_1559_ET = new Date("2026-09-18T19:59:00Z");
const VEN_1600_ET = new Date("2026-09-18T20:00:00Z");
const VEN_0700_ET = new Date("2026-09-18T11:00:00Z"); // pre-market
const VEN_0000_ET = new Date("2026-09-18T04:00:00Z"); // mezzanotte a New York
const VEN_2030_ET = new Date("2026-09-19T00:30:00Z"); // dopo l'after hours
const GIO_2030_ET = new Date("2026-09-18T00:30:00Z");
const SAB_1100_ET = new Date("2026-09-19T15:00:00Z");
const GEN_0930_ET = new Date("2026-01-15T14:30:00Z"); // stessa apertura, ora solare

function nodeEnv(): Record<string, string | undefined> {
  // `@types/node` non e' installato di proposito: qualunque scrittura npm su
  // Windows puo' togliere il ramo Linux dal lockfile. Vedi localDate.test.ts.
  return (globalThis as unknown as { process: { env: Record<string, string | undefined> } })
    .process.env;
}
const TZ_ORIGINALE = nodeEnv().TZ;
afterEach(() => { nodeEnv().TZ = TZ_ORIGINALE; });

describe("l'ora di New York non dipende dalla macchina", () => {
  it("rende la stessa lettura sotto qualunque fuso locale", () => {
    const letture = ["Europe/Rome", "America/New_York", "UTC", "Asia/Tokyo"].map((tz) => {
      nodeEnv().TZ = tz;
      return etWallClock(VEN_0930_ET);
    });
    for (const l of letture) {
      expect(l).toEqual({ minutes: RTH_OPEN_MIN, label: "09:30", weekday: 5 });
    }
  });

  it("⚠️ controllo negativo: l'orologio della macchina, invece, cambia", () => {
    /* Senza questa riga il test qui sopra sarebbe vero anche di
     * un'implementazione basata su `getHours()`: e' questa a dimostrare che le
     * quattro letture uguali sono un risultato e non una coincidenza. */
    const ore = ["Europe/Rome", "UTC", "Asia/Tokyo"].map((tz) => {
      nodeEnv().TZ = tz;
      return new Date(VEN_0930_ET).getHours();
    });
    expect(new Set(ore).size).toBeGreaterThan(1);
  });

  it("segue il cambio d'ora invece di uno scostamento fisso", () => {
    // 13:30Z a settembre e 14:30Z a gennaio sono lo stesso momento della
    // seduta: se qualcuno cablasse UTC-4 o UTC-5, una delle due sballerebbe.
    expect(usSessionClock(VEN_0930_ET).etLabel).toBe("09:30");
    expect(usSessionClock(GEN_0930_ET).etLabel).toBe("09:30");
    expect(usSessionClock(GEN_0930_ET).phase).toBe("open");
  });

  it("a mezzanotte a New York legge 0, non 1440", () => {
    // `hour12: false` su certe versioni di ICU rende «24»: il difetto vivrebbe
    // solo nella prima ora del giorno di New York, cioe' quasi mai.
    const c = usSessionClock(VEN_0000_ET);
    expect(c.etMinutes).toBe(0);
    expect(c.etLabel).toBe("00:00");
    expect(c.phase).toBe("closed");
    expect(c.minutesToNext).toBe(4 * 60); // il pre-market apre alle 04:00 ET
  });
});

describe("le fasi della giornata americana", () => {
  it("un minuto prima della campanella e' ancora pre-market", () => {
    const c = usSessionClock(VEN_0929_ET);
    expect(c.phase).toBe("pre");
    expect(c.nextLabel).toBe("apertura");
    expect(c.minutesToNext).toBe(1);
  });

  it("alle 09:30 in punto il mercato e' aperto e l'avanzamento riparte da zero", () => {
    const c = usSessionClock(VEN_0930_ET);
    expect(c.phase).toBe("open");
    expect(c.progress).toBe(0);
    expect(c.minutesToNext).toBe(RTH_CLOSE_MIN - RTH_OPEN_MIN);
  });

  it("alle 15:59 e' aperto, alle 16:00 e' after hours", () => {
    expect(usSessionClock(VEN_1559_ET).phase).toBe("open");
    const dopo = usSessionClock(VEN_1600_ET);
    expect(dopo.phase).toBe("after");
    expect(dopo.progress).toBe(0);
    expect(dopo.minutesToNext).toBe(AFTER_CLOSE_MIN - RTH_CLOSE_MIN);
  });

  it("nel pre-market dice quanto manca all'apertura e a che punto e' la finestra", () => {
    const c = usSessionClock(VEN_0700_ET);
    expect(c.phase).toBe("pre");
    expect(c.minutesToNext).toBe(150);
    expect(c.progress).toBeCloseTo(180 / 330, 3); // 04:00 → 09:30
  });
});

describe("quando il prossimo passaggio non e' oggi", () => {
  it("il venerdi' dopo l'after hours nomina lunedi' invece di un conto alla rovescia", () => {
    const c = usSessionClock(VEN_2030_ET);
    expect(c.phase).toBe("closed");
    expect(c.minutesToNext).toBeNull(); // attraversare la mezzanotte e' un altro conto
    expect(c.nextDayLabel).toBe("lunedì");
  });

  it("gli altri giorni dice domani", () => {
    expect(usSessionClock(GIO_2030_ET).nextDayLabel).toBe("domani");
  });

  it("il sabato non ha nemmeno il pre-market", () => {
    const c = usSessionClock(SAB_1100_ET);
    expect(c.weekend).toBe(true);
    expect(c.phase).toBe("closed");
    expect(c.progress).toBeNull();
    expect(c.nextDayLabel).toBe("lunedì");
  });
});

describe("formatDelta", () => {
  it("scrive ore e minuti, e non dice mai zero", () => {
    expect(formatDelta(72)).toBe("1h 12m");
    expect(formatDelta(48)).toBe("48m");
    expect(formatDelta(0.4)).toBe("meno di un minuto");
    expect(formatDelta(-1)).toBe("—");
  });
});
