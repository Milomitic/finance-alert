import { describe, expect, it } from "vitest";

/* ─── L'ordine dei tre blocchi della pagina Segnali ───────────────────────
 *
 * confluenze → filtri → tabella, e non e' un gusto: e' la sequenza di cio' che
 * si fa. Le confluenze sono un digest da leggere per primo, e cliccare un
 * cluster RESTRINGE la tabella — cioe' e' esso stesso un filtro. Coi controlli
 * in cima, il primo comando della pagina agiva su una tabella non ancora vista.
 *
 * ⚠️ Pinnato alla SORGENTE e non a un render. jsdom non fa layout, ma qui non
 * serve: l'ordine di lettura di una colonna e' l'ordine nel DOM, e l'ordine nel
 * DOM e' l'ordine nel JSX. Montare la pagina intera costerebbe di finti quanto
 * l'intera pagina e misurerebbe la stessa cosa.
 */

const SORGENTI = import.meta.glob("/src/pages/AlertsPage.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

describe("pagina Segnali — ordine dei blocchi", () => {
  const src = Object.values(SORGENTI)[0] ?? "";

  it("la sorgente viene letta davvero", () => {
    /* Il pavimento: `indexOf` su una stringa vuota torna -1 per tutto, e
     * `-1 < -1` e' falso — quindi senza questo il test sotto fallirebbe per la
     * ragione sbagliata, o passerebbe se qualcuno lo scrivesse con `<=`. */
    expect(src.length).toBeGreaterThan(2000);
  });

  it("confluenze, poi filtri, poi tabella", () => {
    const confluenze = src.indexOf("<AlertsInsightCard");
    const filtri = src.indexOf("<AlertFilters");
    const tabella = src.indexOf("<AlertsTable");
    expect(confluenze, "AlertsInsightCard non e' piu' montata").toBeGreaterThan(-1);
    expect(filtri, "AlertFilters non e' piu' montato").toBeGreaterThan(-1);
    expect(tabella, "AlertsTable non e' piu' montata").toBeGreaterThan(-1);
    expect(confluenze, "i filtri devono stare SOTTO le confluenze").toBeLessThan(filtri);
    expect(filtri, "i filtri devono stare SOPRA la tabella").toBeLessThan(tabella);
  });
});
