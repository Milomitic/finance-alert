import { describe, expect, it } from "vitest";

/* ─── Cambiare timeframe non e' cambiare pagina ────────────────────────────
 *
 * Difetto riportato dall'utente il 2026-09-17: «i grafici mi riportano in alto
 * nella pagina quando cambio timeframe».
 *
 * La causa non e' nel grafico. Il timeframe vive nell'URL (`?range=`), e
 * scriverlo con `setSearchParams(...)` senza opzioni e' un PUSH, cioe' una
 * voce di cronologia nuova. `useScrollRestoration` fa esattamente cio' che
 * dichiara: una pagina nuova comincia dall'alto, quindi porta `<main>` a
 * `scrollTop = 0`. Con `replace` la regola non si applica — ed e' la stessa
 * scelta che i filtri fanno altrove — perche' questa e' la stessa pagina con
 * un'altra vista.
 *
 * ⚠️ In piu' il push riempiva la cronologia: dopo aver provato cinque
 * timeframe, «indietro» ne ripercorreva cinque invece di tornare da dove si
 * era arrivati.
 *
 * Perche' un censimento della SORGENTE e non un test che monta la pagina:
 * `StockDetailPage` monta tre grafici `lightweight-charts`, che in jsdom non
 * hanno un canvas su cui disegnare. La stessa ragione — e la stessa forma —
 * di `stockDetailLayout.test.ts` qui accanto.
 */

const SORGENTI = import.meta.glob("/src/pages/StockDetailPage.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

/** Le chiamate a `setSearchParams` che NON passano `{ replace: true }`. */
export function scrittureCheCreanoCronologia(sorgente: string): string[] {
  const chiamate = sorgente.match(/setSearchParams\([\s\S]*?\);/g) ?? [];
  return chiamate.filter((c) => !/replace:\s*true/.test(c));
}

describe("il timeframe scrive l'URL senza creare una voce di cronologia", () => {
  const sorgente = Object.values(SORGENTI)[0] ?? "";

  it("la sorgente viene letta davvero", () => {
    // Il pavimento: senza, ogni asserzione sotto sarebbe vera di un file vuoto
    // — un glob che smette di risolvere renderebbe il controllo muto.
    expect(sorgente.length).toBeGreaterThan(1000);
    expect(sorgente).toContain("RangeSelector");
  });

  it("ogni scrittura del range usa `replace`", () => {
    const chiamate = sorgente.match(/setSearchParams\([\s\S]*?\);/g) ?? [];
    // Pavimento sul NUMERO: il selettore e il collegamento «Passa a 1G».
    expect(chiamate.length).toBeGreaterThanOrEqual(2);
    expect(scrittureCheCreanoCronologia(sorgente)).toEqual([]);
  });

  it("⚠️ il censimento SA vedere una scrittura in push", () => {
    // Senza questo, «nessuna scrittura in push» sarebbe vero anche di un
    // matcher che non trova mai niente.
    const finto = "setSearchParams({ range: r });";
    expect(scrittureCheCreanoCronologia(finto)).toHaveLength(1);
    expect(scrittureCheCreanoCronologia("setSearchParams({ range: r }, { replace: true });")).toEqual([]);
  });
});
