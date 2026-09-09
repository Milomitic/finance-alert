import { describe, expect, it, vi } from "vitest";

import { parseAll, parseStored, toStored } from "./screenerViews";

/* The screener persisted three things separately and none of them together:
 * filter presets, column visibility, and a sort that lived only in the URL. A
 * saved view is all three, which is what makes a search resumable.
 *
 * ⚠️ The load-bearing property is BACKWARD COMPATIBILITY. Whatever presets a
 * user already has sit in localStorage as bare filter objects with no version
 * marker. Reading them as "not a view" and dropping them would destroy saved
 * work with no undo, and it would look like a clean new feature.
 */

type Filters = { minScore?: number; sector?: string };

// Stands in for the real `normalizePreset`, which merges over EMPTY_FILTERS so
// fields added after a preset was saved get sane defaults.
const normalize = (raw: unknown): Filters => ({
  minScore: undefined,
  sector: undefined,
  ...(typeof raw === "object" && raw !== null ? raw : {}),
});

const DEFAULTS = { sortBy: "ticker", sortDir: "asc" } as const;

describe("i preset gia salvati dall'utente continuano a funzionare", () => {
  it("legge la vecchia forma, che e solo i filtri", () => {
    const v1 = { minScore: 60, sector: "Technology" };

    const view = parseStored<Filters>(v1, DEFAULTS, normalize);

    expect(view).not.toBeNull();
    expect(view!.filters).toMatchObject({ minScore: 60, sector: "Technology" });
  });

  it("a un preset v1 assegna l'ordinamento PREDEFINITO, non quello corrente", () => {
    // Applying an old preset must leave the table in a known state. Inheriting
    // whatever sort happened to be active would make the same preset behave
    // differently depending on what the user did just before.
    const view = parseStored<Filters>({ minScore: 60 }, DEFAULTS, normalize);

    expect(view!.sortBy).toBe("ticker");
    expect(view!.sortDir).toBe("asc");
  });

  it("un preset v1 non nasconde alcuna colonna", () => {
    const view = parseStored<Filters>({ minScore: 60 }, DEFAULTS, normalize);
    expect(view!.hiddenColumns).toEqual([]);
  });
});

describe("la forma nuova conserva tutto", () => {
  it("fa il giro completo senza perdere nulla", () => {
    const view = {
      filters: { minScore: 70, sector: "Energy" },
      sortBy: "score",
      sortDir: "desc" as const,
      hiddenColumns: ["rsi", "volume"],
    };

    const back = parseStored<Filters>(toStored(view), DEFAULTS, normalize);

    expect(back).toEqual({
      filters: expect.objectContaining({ minScore: 70, sector: "Energy" }),
      sortBy: "score",
      sortDir: "desc",
      hiddenColumns: ["rsi", "volume"],
    });
  });

  it("memorizza le colonne NASCOSTE, non quelle visibili", () => {
    // The inversion matters: storing the visible set would make every column
    // added to the table later invisible inside every previously saved view.
    const stored = toStored({
      filters: {},
      sortBy: "ticker",
      sortDir: "asc",
      hiddenColumns: ["volume"],
    });

    expect(stored.hiddenColumns).toEqual(["volume"]);
  });

  it("ordina le colonne, così due viste uguali non differiscono per l'ordine", () => {
    const a = toStored({ filters: {}, sortBy: "t", sortDir: "asc", hiddenColumns: ["b", "a"] });
    const b = toStored({ filters: {}, sortBy: "t", sortDir: "asc", hiddenColumns: ["a", "b"] });

    expect(a.hiddenColumns).toEqual(b.hiddenColumns);
  });
});

describe("dati corrotti costano il record, non la funzione", () => {
  it("scarta una direzione di ordinamento non valida invece di propagarla", () => {
    const view = parseStored<Filters>(
      { v: 2, filters: {}, sortBy: "score", sortDir: "obliquo" },
      DEFAULTS,
      normalize,
    );

    expect(view!.sortDir).toBe("asc");
  });

  it("ignora voci di colonna che non sono stringhe", () => {
    const view = parseStored<Filters>(
      { v: 2, filters: {}, hiddenColumns: ["rsi", 42, null, "volume"] },
      DEFAULTS,
      normalize,
    );

    expect(view!.hiddenColumns).toEqual(["rsi", "volume"]);
  });

  it("una vista illeggibile non porta via le altre", () => {
    // Ten saved views and one bad record should cost the record.
    const all = parseAll<Filters>(
      { buona: { minScore: 10 }, rotta: "non un oggetto", altra: { v: 2, filters: {} } },
      DEFAULTS,
      normalize,
    );

    expect(Object.keys(all).sort()).toEqual(["altra", "buona"]);
  });

  it("un blob che non e un oggetto non fa esplodere il menu", () => {
    expect(parseAll<Filters>("[]", DEFAULTS, normalize)).toEqual({});
    expect(parseAll<Filters>(null, DEFAULTS, normalize)).toEqual({});
  });

  it("i filtri passano sempre dalla normalizzazione", () => {
    // A view saved before a filter field existed must come back with a sane
    // default for it, not with the field missing.
    const spy = vi.fn(normalize);

    parseStored<Filters>({ v: 2, filters: { minScore: 5 } }, DEFAULTS, spy);

    expect(spy).toHaveBeenCalledWith({ minScore: 5 });
  });
});
