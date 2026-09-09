import { afterEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_RANGE, isValidRange, readRange, resolveRange, writeRange } from "./chartPrefs";

/* Il timeframe del grafico, ricordato fra una visita e l'altra.
 *
 * La regola che quasi tutto questo file difende: **l'URL vince**. Un link
 * `?range=1h` deve aprirsi a 1h per chiunque lo riceva, altrimenti due persone
 * guardano grafici diversi dallo stesso indirizzo e chi lo ha mandato non ha
 * modo di accorgersene. La preferenza salvata e un DEFAULT, non un override.
 */

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("l'URL vince sulla preferenza salvata", () => {
  it("un link esplicito ignora quello che l'utente guarda di solito", () => {
    writeRange("1w");

    expect(resolveRange("1h")).toBe("1h");
  });

  it("senza indicazione nell'URL si usa la preferenza", () => {
    writeRange("1h");

    expect(resolveRange(null)).toBe("1h");
  });

  it("senza ne l'una ne l'altra si torna al default", () => {
    expect(resolveRange(null)).toBe(DEFAULT_RANGE);
  });
});

describe("un valore memorizzato non e automaticamente valido", () => {
  it("una chiave che questa build non serve piu viene ignorata", () => {
    // Lo storage sopravvive ai rilasci e si condivide fra schede: puo tenere
    // un timeframe che il selettore non offre piu. Passarlo all'API sarebbe
    // una richiesta che nessuno ha fatto.
    localStorage.setItem("chart-timeframe", "4h");

    expect(readRange()).toBeNull();
    expect(resolveRange(null)).toBe(DEFAULT_RANGE);
  });

  it("nemmeno un URL puo imporre un timeframe inesistente", () => {
    expect(resolveRange("3anni")).toBe(DEFAULT_RANGE);
  });

  it("gli alias legacy restano validi", () => {
    // `all` non e piu nel selettore ma i vecchi link lo usano e l'API lo
    // risolve ancora.
    expect(isValidRange("all")).toBe(true);
  });

  it("non si salva un timeframe che non esiste", () => {
    writeRange("4h");

    expect(readRange()).toBeNull();
  });
});

describe("lo storage puo non esserci, e non e un errore da mostrare", () => {
  it("una lettura che lancia degrada al default", () => {
    // Finestra anonima, browser che blocca i dati di sito, cattura di
    // anteprima: l'accesso stesso puo lanciare. Una preferenza non leggibile
    // non deve portarsi giu la pagina.
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("access denied");
    });

    expect(readRange()).toBeNull();
    expect(resolveRange(null)).toBe(DEFAULT_RANGE);
  });

  it("una scrittura che lancia non propaga", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota exceeded");
    });

    expect(() => writeRange("1h")).not.toThrow();
  });
});
