import { describe, expect, it } from "vitest";

import {
  GAP_NOTABLE_SECTOR,
  GAP_TEXT,
  GAP_TYPICAL_STOCK,
  formatGap,
  lensGapOf,
} from "./lensGap";
import { lensGap } from "./sectorLens";
// ⚠️ `?raw` di Vite, non `node:fs`: questo pacchetto non ha `@types/node`, e
// un test che legge un file con `readFileSync` gira sotto vitest e fa fallire
// `tsc -b`, cioe' la build — verde in locale, rosso in CI.
import sectorTableSource from "@/components/sectors/SectorLensTable.tsx?raw";
import type { SectorSummary } from "@/hooks/useSectorDetail";

/* Il Divario fra le due lenti, adesso su due pagine.
 *
 * Esplora lo calcolava per gli undici settori; lo screener ha le due lenti
 * sulla stessa riga da sempre e non ne faceva la differenza. Due definizioni
 * separate potrebbero divergere di SEGNO, e nessuno dei due schermi lo direbbe.
 */

describe("il segno e la convenzione, non una scelta libera", () => {
  it("positivo quando il prezzo corre davanti ai fondamentali", () => {
    // Qualita 40, Tecnico 80: il Tecnico e avanti.
    expect(lensGapOf(40, 80)).toBe(40);
  });

  it("negativo quando i fondamentali sono davanti al prezzo", () => {
    // Il titolo dell'audit: Qualita 81, Tecnico 40.
    expect(lensGapOf(81, 40)).toBe(-41);
  });

  it("zero quando coincidono, ed e un valore vero", () => {
    // ⚠️ Distinto da «ignoto». Sotto si asserisce che l'ignoto sia null.
    expect(lensGapOf(55, 55)).toBe(0);
  });
});

describe("una lente sola non vale zero", () => {
  it.each([
    { name: "manca la Qualita", q: null, t: 60 },
    { name: "manca il Tecnico", q: 60, t: null },
    { name: "mancano entrambe", q: null, t: null },
    { name: "un valore non finito", q: 60, t: Number.NaN },
  ])("$name → null", ({ q, t }) => {
    // Zero significa «le due coincidono». Restituirlo per un dato che non
    // abbiamo lo farebbe comparire in mezzo alla classifica fra i titoli in
    // accordo, invece che in fondo con gli sconosciuti.
    expect(lensGapOf(q, t)).toBeNull();
  });
});

describe("le due pagine non possono divergere", () => {
  function sec(over: Partial<SectorSummary>): SectorSummary {
    return { name: "X", avg_score: null, avg_technical: null, ...over } as SectorSummary;
  }

  it.each([
    { name: "Financials", avg_score: 54.8, avg_technical: 66.0 },
    { name: "Utilities", avg_score: 57.3, avg_technical: 43.6 },
  ])("$name legge lo stesso numero da entrambe le porte", (row) => {
    // ⚠️ Il test che protegge dalla divergenza: se qualcuno «sistemasse» il
    // segno da una parte sola, questa riga sarebbe l'unica cosa a dirlo.
    const daiSettori = lensGap(sec(row));
    const dalloScreener = lensGapOf(row.avg_score, row.avg_technical);

    expect(daiSettori).toBe(dalloScreener);
  });

  it("i valori storici della tabella settori restano quelli", () => {
    expect(lensGap(sec({ avg_score: 54.8, avg_technical: 66.0 }))!).toBeCloseTo(11.2, 5);
    expect(lensGap(sec({ avg_score: 57.3, avg_technical: 43.6 }))!).toBeCloseTo(-13.7, 5);
  });
});

describe("il segno si vede anche quando e positivo", () => {
  it.each([
    { name: "positivo col piu davanti", gap: 11.24, atteso: "+11.2" },
    { name: "negativo col meno", gap: -13.7, atteso: "-13.7" },
    { name: "zero senza segno", gap: 0, atteso: "0.0" },
    { name: "ignoto come trattino", gap: null, atteso: "—" },
  ])("$name", ({ gap, atteso }) => {
    expect(formatGap(gap)).toBe(atteso);
  });

  it("lo screener lo stampa senza decimali", () => {
    expect(formatGap(-40.6, 0)).toBe("-41");
  });
});

describe("il Divario non prende la tavolozza della direzione", () => {
  it("la classe del testo non e ne rosa ne smeraldo", () => {
    // ⚠️ In questo progetto rosa e smeraldo significano una cosa sola:
    // direzione di mercato, giu e su. Il Divario non e una direzione — +20 e
    // −20 sono due oggetti diversi, non «buono» e «cattivo» — e lo studio
    // score-IC dice che il composito Qualita non prevede i rendimenti, quindi
    // colorarlo cosi affermerebbe un ordinamento che le prove negano.
    expect(GAP_TEXT).not.toMatch(/rose|emerald|red|green/);
  });

  it("nessuna delle due tabelle colora il Divario per direzione", () => {
    // Il controllo strutturale: la classe potrebbe restare neutra qui e la
    // tabella settori riapplicare `toneClass` alla propria cella. Si legge la
    // sorgente, perche jsdom non calcola gli stili e il colore non e
    // osservabile in un render.
    const src = sectorTableSource;
    // `toneClass` sopravvive per Δ%, che e una direzione VERA. Deve restare
    // usato una volta sola.
    const usi = src.match(/toneClass\(/g) ?? [];
    expect(usi).toHaveLength(2); // la definizione + la sola cella Δ%
    expect(src).toContain("toneClass(s.change_pct)");
    expect(src).not.toContain("toneClass(gap)");
  });
});

describe("le soglie dichiarano su cosa sono state misurate", () => {
  it("la soglia dei settori resta agli 8 punti", () => {
    expect(GAP_NOTABLE_SECTOR).toBe(8);
  });

  it("il tipico di un singolo titolo NON e zero", () => {
    // ⚠️ Il fatto che impedisce di leggere male la colonna. Misurato in
    // produzione il 2026-09-10 su 925 titoli con entrambe le lenti: mediana
    // -12,7, e solo il 31% dei titoli ha Divario positivo. Le due lenti sono
    // entrambe su 0-100 ma non sono centrate allo stesso modo, quindi un
    // Divario di 0 NON vuol dire «le due concordano».
    expect(GAP_TYPICAL_STOCK).toBeLessThan(-5);
  });

  it("la soglia dei settori sarebbe inutile sui titoli, e il codice lo dice", () => {
    // Con mediana |Divario| 17,9, gli 8 punti marcherebbero il 77% delle
    // righe. Un marcatore che si accende su tre righe su quattro non marca
    // niente — ed e per questo che lo screener non marca affatto.
    expect(Math.abs(GAP_TYPICAL_STOCK)).toBeGreaterThan(GAP_NOTABLE_SECTOR);
  });
});
