import { describe, expect, it } from "vitest";

/* Nessun testo sotto gli 11px, e nessun corpo scritto in px (fase 3, B-01,
 * A-42).
 *
 * Misurato dal vivo il 2026-11-17: il corpo minimo restava 9,5px anche a
 * 1920-3840, mentre tutto il resto cresceva col corpo radice (17 -> 19px).
 * Le classi `text-[10px]` sono ASSOLUTE e non seguono la scala; le rem si'.
 * Il pavimento e' 0.6471rem = 11px alla radice di 17.
 *
 * Fissato sulla SORGENTE, come gli altri censimenti: jsdom non calcola
 * corpi. Con un pavimento sul numero di file letti, perche' un glob che
 * smette di risolvere renderebbe il test vero di niente. */

const SORGENTI = import.meta.glob("/src/**/*.{ts,tsx}", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const PAVIMENTO_REM = 0.6471;

function voci(): { file: string; classe: string }[] {
  const out: { file: string; classe: string }[] = [];
  for (const [file, src] of Object.entries(SORGENTI)) {
    if (file.includes(".test.") || file.includes("/test/")) continue;
    for (const m of src.matchAll(/text-\[([0-9.]+)(px|rem)\]/g)) {
      out.push({ file: file.split("/").pop() ?? file, classe: m[0] });
    }
  }
  return out;
}

describe("corpi minimi", () => {
  it("il glob risolve davvero dei file", () => {
    expect(Object.keys(SORGENTI).length).toBeGreaterThanOrEqual(300);
  });

  it("nessun corpo di testo scritto in px: non seguirebbe la scala", () => {
    expect(voci().filter((v) => v.classe.endsWith("px]")).map((v) => `${v.file}: ${v.classe}`)).toEqual([]);
  });

  it("nessun corpo sotto gli 11px", () => {
    const sotto = voci().filter((v) => {
      const n = Number(v.classe.match(/[0-9.]+/)?.[0]);
      return v.classe.endsWith("rem]") && n < PAVIMENTO_REM;
    });
    expect(sotto.map((v) => `${v.file}: ${v.classe}`)).toEqual([]);
  });

  it("il censimento vede davvero delle classi", () => {
    // Il controllo negativo: senza questo, una regex sbagliata renderebbe
    // le due asserzioni sopra vere di un elenco vuoto.
    expect(voci().length).toBeGreaterThan(400);
  });
});
