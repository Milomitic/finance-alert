import { describe, expect, it } from "vitest";

/* Un'etichetta `sr-only` dentro una lista che scorre deve restarci (A-50).
 *
 * `.sr-only` e' `position: absolute`. Se nessun antenato DENTRO il contenitore
 * che scorre e' posizionato, il suo blocco contenitore sta fuori, il
 * contenitore non la ritaglia, e l'etichetta allunga la pagina che la
 * contiene. Misurato in produzione il 2026-11-17: 185 «, preferito» nella
 * lista «Valutazioni analisti» portavano la dashboard da 4.072 a 12.116px a
 * 1440, cioe' 8.000px di pagina vuota sotto l'ultima scheda. Col database di
 * sviluppo non si vedeva: i preferiti erano pochi.
 *
 * jsdom non fa layout, quindi la regola si fissa sulla SORGENTE: nei file
 * che usano `sr-only`, ogni contenitore `overflow-auto`/`overflow-y-auto`
 * porta `relative`, salvo le eccezioni dichiarate con la ragione. */

const SORGENTI = import.meta.glob("/src/**/*.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

/** file:frammento della classe -> perche' non serve `relative`. */
const ECCEZIONI: Record<string, string> = {
  "AlertDetailDialog.tsx:DialogContent": "il contenuto del dialogo e' `fixed`, quindi gia' posizionato",
  "SetupDetailDialog.tsx:DialogContent": "il contenuto del dialogo e' `fixed`, quindi gia' posizionato",
  "AlertDetailDialog.tsx:<pre": "testo JSON preformattato, nessuna etichetta dentro",
  "Layout.tsx:<nav": "le etichette nascoste del menu non sono nella parte che scorre",
  "Layout.tsx:<main": "il contenitore di tutta l'app: non va posizionato per una sola lista",
  "Layout.tsx:<div className=\"flex-1 overflow-y-auto\"": "il menu a tendina del telefono, senza etichette nascoste",
};

function contenitoriScoperti(): string[] {
  const out: string[] = [];
  for (const [file, src] of Object.entries(SORGENTI)) {
    if (file.includes(".test.") || !src.includes("sr-only")) continue;
    const nome = file.split("/").pop() ?? file;
    for (const riga of src.split("\n")) {
      if (!/className="[^"]*\boverflow-(y-)?auto\b[^"]*"/.test(riga) || /\brelative\b/.test(riga)) continue;
      const esente = Object.keys(ECCEZIONI).some((k) => {
        const [f, frammento] = [k.slice(0, k.indexOf(":")), k.slice(k.indexOf(":") + 1)];
        return nome === f && riga.includes(frammento);
      });
      if (!esente) out.push(`${nome}: ${riga.trim().slice(0, 90)}`);
    }
  }
  return out;
}

describe("etichette sr-only dentro i contenitori che scorrono", () => {
  it("il glob risolve davvero dei file", () => {
    expect(Object.keys(SORGENTI).length).toBeGreaterThanOrEqual(150);
  });

  it("ogni contenitore che scorre, in un file con sr-only, e' posizionato", () => {
    expect(contenitoriScoperti()).toEqual([]);
  });

  it("la lista degli analisti, che ha causato il difetto, e' coperta", () => {
    const src = Object.entries(SORGENTI).find(([f]) => f.endsWith("AnalystActionsCard.tsx"))?.[1] ?? "";
    expect(src).toContain("sr-only");
    expect((src.match(/<ul className="relative flex-1 min-h-0 overflow-y-auto">/g) ?? []).length).toBe(2);
  });
});
