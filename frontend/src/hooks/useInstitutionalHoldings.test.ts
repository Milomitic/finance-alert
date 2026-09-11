import { describe, expect, it } from "vitest";

import { holdingsShown, nextOffset, PAGE_SIZE } from "./useInstitutionalHoldings";

/* ─── Le holdings arrivano a pagine, gli aggregati no ─────────────────────
 *
 * FA-034. Il frontend mappava l'intero array senza `slice`, virtualizzazione
 * ne `max-h`: uno screenshot interno superava i **302.900 pixel** di altezza.
 * Misurato in produzione, la dichiarazione piu grande porta **7.530 righe**.
 *
 * ⚠️ La paginazione qui ACCUMULA invece di sostituire, e non e una preferenza
 * estetica: la pagina ha aggregati di livello-portafoglio, e un elenco che
 * sostituisce li farebbe calcolare su una finestra scorrevole. Accumulando, il
 * prefisso caricato parte sempre dalla posizione piu pesante.
 *
 * ⚠️ Ma accumulare NON basta, ed e il motivo per cui il backend manda
 * `composition` a parte: le uscite hanno peso zero, quindi nell'ordinamento
 * per peso stanno in fondo e nessun prefisso ragionevole le contiene — 1.301
 * su 7.530 nella dichiarazione maggiore.
 */

describe("la finestra caricata", () => {
  it("parte da una pagina sola, non da tutto", () => {
    expect(PAGE_SIZE).toBeGreaterThan(0);
    expect(PAGE_SIZE).toBeLessThanOrEqual(200);
  });

  it("mostra quante righe sono caricate, non quante ne esistono", () => {
    expect(holdingsShown(7530, 0)).toBe(PAGE_SIZE);
    expect(holdingsShown(7530, 1)).toBe(PAGE_SIZE * 2);
  });

  it("non promette piu righe di quante la dichiarazione ne abbia", () => {
    expect(holdingsShown(30, 0)).toBe(30);
    expect(holdingsShown(30, 5)).toBe(30);
  });

  it("l'offset successivo e nullo quando non c'e piu niente da chiedere", () => {
    expect(nextOffset(7530, PAGE_SIZE)).toBe(PAGE_SIZE);
    expect(nextOffset(30, 30)).toBeNull();
    expect(nextOffset(0, 0)).toBeNull();
  });

  it("⚠️ un totale sconosciuto non promette altre pagine", () => {
    /* Meglio un pulsante assente che uno che chiede una pagina inesistente.
     *
     * ⚠️ Onesta sul limite di questo controllo: togliendo la guardia esplicita
     * il test resta VERDE, perche in JavaScript `100 < undefined` e comunque
     * falso. Quindi misura il CONTRATTO, non la riga — e il contratto e quello
     * che conta, ma un `totale ?? 0` introdotto in futuro lo romperebbe senza
     * che questo test se ne accorga. La guardia resta perche rende l'intento
     * leggibile, non perche sia lei a produrre il risultato. */
    expect(nextOffset(undefined, 100)).toBeNull();
  });
});
