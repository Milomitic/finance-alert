import { describe, expect, it } from "vitest";

import source from "./DayCell.tsx?raw";

/* Su un calendario earnings il ticker E' l'informazione.
 *
 * Le pastiglie rendevano il logo e una lettera: `D ▲`, `A…`, `O…`. La causa
 * era la disposizione, non il chip: la cella e' un settimo della griglia, e
 * dividerla in due colonne lascia ~71px per pastiglia — meno di quanto serva
 * a un ticker.
 *
 * ⚠️ Questo difetto era GIA' stato trovato e GIA' corretto, e la correzione
 * aveva la soglia sbagliata. Il commento in `DayCell` lo racconta per esteso:
 * due colonne "made the tickers vanish", trentuno etichette invisibili, e il
 * rimedio fu spostarle a `dense-3` (1400px) sul calcolo "due chip da 85px".
 * Ma 85px non contengono un ticker, e lo screenshot che ha riaperto il caso e'
 * stato preso a **1440px**, cioe' dentro il ramo a due colonne.
 *
 * Rifatto il conto, due colonne leggibili vorrebbero un viewport oltre i
 * 1480px. Invece di rincorrere la soglia: una colonna sempre. Il "+N" esiste
 * gia' ed e' onesto; una fila di pastiglie senza nome no.
 *
 * ⚠️ LIMITE. jsdom non calcola gli stili, quindi il troncamento non e'
 * osservabile qui e questo test non lo misura: fissa la DECISIONE, cioe' che
 * nessuno rimetta un ramo a due colonne senza rifare il conto. Che il ticker
 * si legga si vede solo su un browser vero.
 */

describe("la cella del giorno non divide le pastiglie in due colonne", () => {
  it("non esiste un ramo a due colonne a nessun breakpoint", () => {
    // Qualunque `<qualcosa>:grid-cols-2` sulla griglia delle pastiglie
    // rimetterebbe il difetto sopra quella larghezza.
    expect(source).not.toMatch(/grid-cols-1[^"]*grid-cols-2/);
  });

  it("la griglia delle pastiglie resta a una colonna", () => {
    expect(source).toContain("grid grid-cols-1 gap-x-1 gap-y-1");
  });
});

describe("l'overflow onesto resta al suo posto", () => {
  it("le pastiglie in eccesso diventano un +N invece di sparire", () => {
    // Il controllo negativo della decisione sopra: passare a una colonna
    // riduce le pastiglie visibili, quindi il "+N" deve esserci — altrimenti
    // gli eventi in eccesso non sparirebbero troncati, sparirebbero e basta.
    expect(source).toContain("overflowCount");
  });
});
