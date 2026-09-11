import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { daysUntil, earningsProximityDays } from "./earningsProximity";

/* La regola «la trimestrale cade dentro la finestra» ha due consumatori con
 * finestre diverse — l'orizzonte di un segnale e la vita residua di un setup —
 * e prima di questo file ne esisteva una sola copia, privata dentro
 * `AlertDetailDialog`. Due copie della stessa regola divergono in silenzio:
 * e la lezione di `lib/money.ts` (cinque formattatori) e di `lib/lensGap.ts`
 * (due definizioni del segno). */

// Un martedi pomeriggio, ora locale: la mezzanotte di riferimento e quella
// LOCALE, mentre una data ISO senza ora viene letta come mezzanotte UTC.
/** `process.env` senza dipendere da `@types/node`.
 *
 *  ⚠️ Il pacchetto NON va installato per questo. Qualunque scrittura npm su
 *  Windows puo togliere dal lockfile le dipendenze opzionali Linux, e il
 *  difetto e invisibile in locale: `npm ci` e `npm run build` passano qui e
 *  solo la CI su Linux li vede. E costato cinque occorrenze; una dichiarazione
 *  di tre righe non vale quel rischio.
 *
 *  Node rilegge `process.env.TZ` a ogni operazione su Date, anche dopo che una
 *  Date e gia stata costruita — verificato prima di scrivere questo test. */
function nodeEnv(): Record<string, string | undefined> {
  return (globalThis as unknown as { process: { env: Record<string, string | undefined> } })
    .process.env;
}

const OGGI = new Date(2026, 8, 11, 14, 30, 0);

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(OGGI);
});
afterEach(() => vi.useRealTimers());

describe("daysUntil", () => {
  it("conta i giorni fino a una data futura", () => {
    expect(daysUntil("2026-09-18")).toBe(7);
  });

  it("oggi vale zero, non uno", () => {
    expect(daysUntil("2026-09-11")).toBe(0);
  });

  it("una data passata e NEGATIVA, non nulla: distinguere e compito del chiamante", () => {
    expect(daysUntil("2026-09-04")).toBe(-7);
  });

  it("⚠️ arrotonda invece di troncare, e il test deve stare A OVEST per provarlo", () => {
    /* `2026-09-18` e mezzanotte UTC; «oggi» e mezzanotte LOCALE. La
     * differenza vale `n + offset`, dove l'offset e lo scostamento del fuso:
     *
     *   Roma (UTC+2)      n + 0,083   →  floor = round = n     IDENTICI
     *   CI (UTC)          n           →  floor = round = n     IDENTICI
     *   New York (UTC-4)  n − 0,208   →  floor = n−1 ≠ round   DIVERGONO
     *
     * ⚠️ Scritto senza forzare il fuso, questo test PASSA anche sostituendo
     * `Math.round` con `Math.floor` — verificato: e vacuo sia su una macchina
     * europea sia in CI, che gira in UTC. Sarebbe la terza istanza in questo
     * repo di un test vero di niente, dopo `toEqual` sui nodi DOM e la scheda
     * filtri con tre aree chiuse. Il fuso va imposto, altrimenti la sola
     * piattaforma su cui il difetto esiste e l'unica dove nessuno lo esegue.
     */
    const env = nodeEnv();
    const tz = env.TZ;
    try {
      env.TZ = "America/New_York";
      vi.setSystemTime(new Date(2026, 8, 11, 14, 30, 0));
      for (let g = 0; g <= 60; g++) {
        const d = new Date(Date.UTC(2026, 8, 11 + g));
        expect(daysUntil(d.toISOString().slice(0, 10))).toBe(g);
      }
    } finally {
      env.TZ = tz;
      vi.setSystemTime(OGGI);
    }
  });

  it("una data assente o illeggibile e nulla", () => {
    expect(daysUntil(null)).toBeNull();
    expect(daysUntil(undefined)).toBeNull();
    expect(daysUntil("")).toBeNull();
    expect(daysUntil("non-una-data")).toBeNull();
  });

  it("accetta anche la forma con l'ora attaccata che yfinance restituisce", () => {
    expect(daysUntil("2026-09-18 00:00:00")).toBe(7);
  });
});

describe("earningsProximityDays", () => {
  it("dentro la finestra: torna i giorni all'evento", () => {
    expect(earningsProximityDays("2026-09-18", 14)).toBe(7);
  });

  it("il bordo della finestra e DENTRO", () => {
    expect(earningsProximityDays("2026-09-18", 7)).toBe(7);
  });

  it("un giorno oltre il bordo non si marca", () => {
    expect(earningsProximityDays("2026-09-18", 6)).toBeNull();
  });

  it("oggi si marca", () => {
    expect(earningsProximityDays("2026-09-11", 10)).toBe(0);
  });

  it("⚠️ una data gia passata non si marca: e cache stantia, non un evento", () => {
    expect(earningsProximityDays("2026-09-04", 30)).toBeNull();
  });

  it("data sconosciuta non e «nessuna trimestrale», ma non si marca comunque", () => {
    expect(earningsProximityDays(null, 14)).toBeNull();
    expect(earningsProximityDays(undefined, 14)).toBeNull();
  });

  it("finestra sconosciuta non si marca: non si inventa un limite", () => {
    expect(earningsProximityDays("2026-09-18", null)).toBeNull();
  });

  it("⚠️ finestra gia scaduta non marca nulla, nemmeno un evento di oggi", () => {
    // Un setup oltre il proprio tetto ha finestra negativa: qualunque evento
    // e «dopo», e il marcatore direbbe il contrario.
    expect(earningsProximityDays("2026-09-11", -1)).toBeNull();
  });
});

/* ─── Il proprietario unico deve avere davvero un corpo solo ───────────── */

import alertDialogSource from "@/components/AlertDetailDialog.tsx?raw";
import setupRowSource from "@/components/setups/SetupConditionGroup.tsx?raw";

describe("nessun consumatore rifa l'aritmetica per conto proprio", () => {
  /* ⚠️ Controllo sulla SORGENTE, come per il Divario, e per lo stesso motivo:
   * un test di comportamento non distingue una delega da una seconda copia
   * scritta identica. Distingue solo quando le due hanno gia divergiuto —
   * cioe troppo tardi. Il numero magico dei millisecondi in un giorno e la
   * firma dell'aritmetica: se ricompare in un consumatore, la regola e stata
   * riscritta li. */
  const GIORNO_IN_MS = /86[_,]?400[_,]?000/;

  it("il dialogo del segnale delega", () => {
    expect(alertDialogSource).toContain("@/lib/earningsProximity");
    expect(alertDialogSource).not.toMatch(GIORNO_IN_MS);
  });

  it("la riga del setup delega", () => {
    expect(setupRowSource).toContain("@/lib/earningsProximity");
    expect(setupRowSource).not.toMatch(GIORNO_IN_MS);
  });
});
