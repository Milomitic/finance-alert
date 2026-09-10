import { describe, expect, it } from "vitest";

import InstitutionalDetailSource from "./InstitutionalDetailPage.tsx?raw";
import MacroDetailSource from "./MacroDetailPage.tsx?raw";
import MarketDetailSource from "./MarketDetailPage.tsx?raw";
import SectorDetailSource from "./SectorDetailPage.tsx?raw";
import StockDetailSource from "./StockDetailPage.tsx?raw";

/* Ogni pagina di dettaglio deve dire come si torna indietro.
 *
 * Cinque route di dettaglio non compaiono nel menu — titolo, settore, mercato,
 * macro, fondo — quindi ci si arriva solo cliccando. Due non offrivano alcun
 * ritorno, e una delle due e la pagina piu visitata dell'app.
 *
 * ⚠️ E il modello NON e `navigate(-1)`. Un ritorno alla storia del browser non
 * porta da nessuna parte quando la pagina si apre da un link ricevuto — cioe
 * esattamente quando un ritorno serve. Un `<Link>` verso la pagina padre
 * funziona sempre, e per giunta dice DOVE porta prima di essere cliccato.
 *
 * ⚠️ PERCHE' QUESTO TEST LEGGE IL SORGENTE. Montare queste pagine
 * significherebbe montare react-query, il router, i grafici e una decina di
 * hook di rete: si finirebbe per testare l'infrastruttura invece del ritorno.
 * L'alternativa tentata prima era peggio — un finto componente costruito
 * dentro il test, che avrebbe asserito che il TEST rende un'ancora e niente
 * sulle pagine: la "true of nothing" che questo repo continua a togliere.
 *
 * ⚠️ E usa `?raw` di Vite, non `node:fs`. Un primo tentativo leggeva i file con
 * `readFileSync` e `__dirname`: funziona a runtime perche vitest gira su Node,
 * e **rompe `tsc`**, che nel progetto frontend non ha i tipi di Node. Il build
 * e `tsc -b && vite build`, quindi sarebbe morto in CI. `?raw` e tipizzato da
 * `vite/client`, che il tsconfig gia dichiara, e non aggiunge dipendenze — il
 * che conta doppio qui, dove ogni scrittura npm su Windows puo togliere il
 * ramo Linux dal lockfile.
 *
 * Cerca una stringa STABILE, la destinazione, non la formattazione del JSX:
 * riformattare il file non lo rompe, togliere il ritorno si.
 */

/** Pagina di dettaglio -> rotta padre a cui il suo ritorno deve puntare.
 *
 *  Oggetti e non tuple: con `it.each` su un array, `%s` interpola per
 *  POSIZIONE, quindi il titolo del test finiva per contenere l'intero
 *  sorgente della pagina. Con gli oggetti si nomina il campo (`$name`). */
const BACK_TARGET = [
  { name: "StockDetailPage", source: StockDetailSource, target: "/stocks" },
  { name: "MarketDetailPage", source: MarketDetailSource, target: "/" },
  { name: "MacroDetailPage", source: MacroDetailSource, target: "/calendar" },
  { name: "SectorDetailPage", source: SectorDetailSource, target: "/sectors" },
  {
    name: "InstitutionalDetailPage",
    source: InstitutionalDetailSource,
    target: "/institutionals",
  },
];

describe("ogni pagina di dettaglio offre un ritorno", () => {
  it.each(BACK_TARGET)("$name torna a $target", ({ source, target }) => {
    expect(source).toContain(`to="${target}"`);
  });
});

describe("il ritorno e una destinazione, non la storia del browser", () => {
  it.each(BACK_TARGET)(
    "$name non punta a una rotta con segmenti dinamici",
    ({ target }) => {
      // Il controllo negativo: un ritorno verso `/stocks/:ticker` riporterebbe
      // alla pagina da cui si vuole uscire.
      expect(target).not.toContain(":");
    },
  );

  it("le cinque destinazioni sono distinte", () => {
    // Se due pagine puntassero alla stessa, una delle due starebbe tornando
    // al posto sbagliato — e l'assertion sopra non se ne accorgerebbe.
    const targets = BACK_TARGET.map((p) => p.target);
    expect(new Set(targets).size).toBe(targets.length);
  });
});
