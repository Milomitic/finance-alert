import { describe, expect, it, vi } from "vitest";

import {
  CHIAVE,
  FINESTRA_MS,
  installaRicaricaDopoRilascio,
  ricaricaSeServe,
} from "./ricaricaDopoRilascio";
import main from "../main.tsx?raw";

function memoria(): Storage {
  const m = new Map<string, string>();
  return {
    get length() { return m.size; },
    clear: () => m.clear(),
    getItem: (k) => m.get(k) ?? null,
    key: (i) => Array.from(m.keys())[i] ?? null,
    removeItem: (k) => void m.delete(k),
    setItem: (k, v) => void m.set(k, String(v)),
  };
}

describe("ricaricaSeServe", () => {
  it("la prima volta ricarica, e se lo segna", () => {
    const storage = memoria();
    const ricarica = vi.fn();
    expect(ricaricaSeServe({ storage, ricarica, ora: () => 1_000_000 })).toBe(true);
    expect(ricarica).toHaveBeenCalledTimes(1);
    expect(storage.getItem(CHIAVE)).toBe("1000000");
  });

  it("dentro la finestra NON ricarica di nuovo: un chunk che manca davvero non gira in ciclo", () => {
    const storage = memoria();
    const ricarica = vi.fn();
    ricaricaSeServe({ storage, ricarica, ora: () => 1_000_000 });
    expect(ricaricaSeServe({ storage, ricarica, ora: () => 1_000_000 + FINESTRA_MS - 1 })).toBe(false);
    expect(ricarica).toHaveBeenCalledTimes(1);
  });

  it("passata la finestra, il rilascio successivo ricarica di nuovo", () => {
    const storage = memoria();
    const ricarica = vi.fn();
    ricaricaSeServe({ storage, ricarica, ora: () => 1_000_000 });
    expect(ricaricaSeServe({ storage, ricarica, ora: () => 1_000_000 + FINESTRA_MS })).toBe(true);
    expect(ricarica).toHaveBeenCalledTimes(2);
  });

  it("senza storage non ricarica: non saprebbe di averlo gia' fatto", () => {
    const ricarica = vi.fn();
    expect(ricaricaSeServe({ storage: null, ricarica, ora: () => 1 })).toBe(false);
    expect(ricarica).not.toHaveBeenCalled();
  });

  it("uno storage che lancia equivale a nessuno storage", () => {
    const ricarica = vi.fn();
    const rotto = { getItem: () => { throw new Error("bloccato"); }, setItem: () => {} };
    expect(ricaricaSeServe({ storage: rotto, ricarica, ora: () => 1 })).toBe(false);
    expect(ricarica).not.toHaveBeenCalled();
  });

  it("un valore illeggibile nello storage non blocca la ricarica", () => {
    const storage = memoria();
    storage.setItem(CHIAVE, "non-un-numero");
    const ricarica = vi.fn();
    expect(ricaricaSeServe({ storage, ricarica, ora: () => 5 })).toBe(true);
  });
});

describe("installaRicaricaDopoRilascio", () => {
  function finestra() {
    const bersaglio = new EventTarget();
    const reload = vi.fn();
    const win = Object.assign(bersaglio, {
      sessionStorage: memoria(),
      location: { reload },
    }) as unknown as Window;
    return { win, reload };
  }

  it("ricarica all'evento che Vite emette quando un import dinamico fallisce", () => {
    const { win, reload } = finestra();
    installaRicaricaDopoRilascio(win);
    win.dispatchEvent(new Event("vite:preloadError"));
    expect(reload).toHaveBeenCalledTimes(1);
    // Il secondo fallimento della stessa pagina ricaricata non ricarica ancora.
    win.dispatchEvent(new Event("vite:preloadError"));
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("controllo negativo: nessun evento, nessuna ricarica", () => {
    const { win, reload } = finestra();
    installaRicaricaDopoRilascio(win);
    win.dispatchEvent(new Event("error"));
    expect(reload).not.toHaveBeenCalled();
  });
});

it("main.tsx lo installa PRIMA di montare l'app: il primo lazy e' gia' la pagina d'ingresso", () => {
  const installa = main.indexOf("installaRicaricaDopoRilascio()");
  const monta = main.indexOf("createRoot(");
  expect(installa).toBeGreaterThan(-1);
  expect(monta).toBeGreaterThan(-1);
  expect(installa).toBeLessThan(monta);
});
