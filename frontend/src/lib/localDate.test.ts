import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { toLocalIsoDate } from "./localDate";

/* ─── Il giorno che l'utente sta guardando, non quello di Greenwich ───────
 *
 * FA-013. `CalendarPage` scriveva la data nell'URL con
 * `cursor.toISOString().slice(0, 10)` — cioe in UTC — e la RILEGGEVA con
 * `new Date(\`${d}T12:00:00\`)`, cioe in locale. Le due meta non erano
 * d'accordo, e l'asimmetria vive dentro lo stesso componente.
 *
 * ⚠️ Non e una questione di quale fuso sia «giusto»: e che scrivere con un
 * riferimento e leggere con un altro sposta il giorno per una finestra di ore
 * larga quanto lo scostamento del fuso. A Roma e la fascia 00:00-02:00; a New
 * York e la SERA, dalle 19:00 in poi — cioe l'orario in cui un calendario si
 * guarda davvero.
 */

function nodeEnv(): Record<string, string | undefined> {
  // `@types/node` non e installato di proposito: qualunque scrittura npm su
  // Windows puo togliere il ramo Linux dal lockfile. Vedi earningsProximity.
  return (globalThis as unknown as { process: { env: Record<string, string | undefined> } })
    .process.env;
}

const TZ_ORIGINALE = nodeEnv().TZ;
beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  nodeEnv().TZ = TZ_ORIGINALE;
  vi.useRealTimers();
});

describe("toLocalIsoDate", () => {
  it("rende il giorno locale, non quello UTC", () => {
    nodeEnv().TZ = "Europe/Rome";
    // 12 settembre, 00:30 a Roma = 11 settembre 22:30 a Greenwich.
    const d = new Date(2026, 8, 12, 0, 30, 0);
    expect(toLocalIsoDate(d)).toBe("2026-09-12");
    expect(d.toISOString().slice(0, 10)).toBe("2026-09-11"); // il difetto
  });

  it("⚠️ e a ovest di Greenwich sbaglia in avanti, non indietro", () => {
    nodeEnv().TZ = "America/New_York";
    // 10 settembre, 21:00 a New York = 11 settembre 01:00 a Greenwich.
    const d = new Date(2026, 8, 10, 21, 0, 0);
    expect(toLocalIsoDate(d)).toBe("2026-09-10");
    expect(d.toISOString().slice(0, 10)).toBe("2026-09-11"); // il difetto
  });

  it("a mezzogiorno i due coincidono ovunque, ed e per questo che il difetto si nasconde", () => {
    for (const tz of ["Europe/Rome", "America/New_York", "UTC"]) {
      nodeEnv().TZ = tz;
      const d = new Date(2026, 8, 11, 12, 0, 0);
      expect(toLocalIsoDate(d)).toBe("2026-09-11");
      expect(d.toISOString().slice(0, 10)).toBe("2026-09-11");
    }
  });

  it("mese e giorno sono a due cifre", () => {
    nodeEnv().TZ = "Europe/Rome";
    expect(toLocalIsoDate(new Date(2026, 0, 5, 23, 59))).toBe("2026-01-05");
  });

  it("il giro completo torna allo stesso giorno, che e cio che l'URL deve garantire", () => {
    nodeEnv().TZ = "America/New_York";
    const d = new Date(2026, 8, 10, 21, 0, 0);
    // Come `CalendarPage` rilegge: mezzogiorno locale, per stare lontano dai
    // bordi del giorno e dai cambi d'ora.
    const riletto = new Date(`${toLocalIsoDate(d)}T12:00:00`);
    expect(toLocalIsoDate(riletto)).toBe(toLocalIsoDate(d));
  });
});

describe("nessuna pagina scrive una data di calendario in UTC", () => {
  /* Controllo sulla SORGENTE: un test di comportamento sul calendario
   * passerebbe a mezzogiorno, che e quando il difetto non esiste. */
  it("CalendarPage delega invece di usare toISOString", async () => {
    const src = (await import("@/pages/CalendarPage.tsx?raw")).default as string;
    expect(src).not.toMatch(/toISOString\(\)\s*\.\s*slice\(0,\s*10\)/);
    expect(src).toContain("toLocalIsoDate");
  });
});
