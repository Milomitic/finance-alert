import { describe, expect, it } from "vitest";

import {
  SETUP_TONE_BORDER,
  SETUP_TONE_CHIP,
  SETUP_TONE_LABEL,
  SETUP_TONE_TEXT,
  setupTone,
} from "./setupTone";

/* ─── Un setup senza direzione non è un setup ribassista ───────────────────
 *
 * FA-061. Il frontend scriveva `const bull = tone === "bull"` in due
 * componenti. Con quel booleano un terzo tono non produce un terzo caso:
 * produce «ribassista», cioè la direzione SBAGLIATA con la stessa sicurezza
 * di prima. È il difetto che questi test rendono impossibile.
 *
 * Misurato in produzione il 2026-09-14: `squeeze_expansion` è l'unico detector
 * i cui setup convertono in un alert di tono diverso — 63 su 230 collegamenti,
 * il 27%.
 */

describe("setupTone", () => {
  it("lascia passare le due direzioni vere", () => {
    expect(setupTone("bull")).toBe("bull");
    expect(setupTone("bear")).toBe("bear");
  });

  it("⚠️ tutto ciò che non è una direzione diventa «non determinato», MAI ribassista", () => {
    // La stessa regola della valuta mancante, che non diventa dollari: un
    // campo che non si sa leggere è ignoto, non un valore preso a caso.
    for (const raw of ["undetermined", "neutral", "", "BULL", null, undefined]) {
      expect(setupTone(raw)).toBe("undetermined");
    }
  });
});

describe("le classi del tono", () => {
  it("coprono tutti e tre i casi, senza buchi", () => {
    for (const mappa of [SETUP_TONE_TEXT, SETUP_TONE_BORDER, SETUP_TONE_CHIP, SETUP_TONE_LABEL]) {
      for (const tono of ["bull", "bear", "undetermined"] as const) {
        expect(mappa[tono]).toBeTruthy();
      }
    }
  });

  it("⚠️ «non determinato» non indossa i colori del VERSO", () => {
    // In quest'app rosa e smeraldo significano direzione (CLAUDE.md: «un
    // palette per significato»). Un'attesa che per costruzione non ha verso
    // non può vestirli: sarebbe un'affermazione fatta col colore, che nessuno
    // legge come un'affermazione e tutti leggono come un fatto.
    for (const mappa of [SETUP_TONE_TEXT, SETUP_TONE_BORDER, SETUP_TONE_CHIP]) {
      expect(mappa.undetermined).not.toMatch(/rose|emerald|green|red/);
    }
    // Controllo positivo: senza, l'asserzione sopra sarebbe vera anche di una
    // tabella svuotata o rinominata.
    expect(SETUP_TONE_TEXT.bull).toMatch(/emerald/);
    expect(SETUP_TONE_TEXT.bear).toMatch(/rose/);
  });

  it("sono stringhe LETTERALI, non composte a runtime", () => {
    // Il purger di Tailwind vede solo letterali: una classe costruita con un
    // template sparisce dal bundle di produzione senza che si veda in
    // sviluppo. Qui si verifica che non ci siano segnaposto rimasti.
    for (const mappa of [SETUP_TONE_TEXT, SETUP_TONE_BORDER, SETUP_TONE_CHIP]) {
      for (const v of Object.values(mappa)) {
        expect(v).not.toContain("${");
      }
    }
  });
});
