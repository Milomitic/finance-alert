import { describe, expect, it } from "vitest";


import {
  esitoNascostoDallArchivio, filtersFromSearch, searchFromState,
} from "@/lib/alertFilters";

/* Alert filters live in the URL, so a bookmark outlives the UI that made it.
 *
 * The "Probabilità minima" filter and the Probabilità sort were removed on
 * 2026-08-20: measured over 2,246 live signals the value takes one or two
 * distinct values per detector and never exceeds 52 anywhere in the engine, so
 * the filter selected DETECTORS and the sort ordered by detector. Links made
 * before the removal still carry the parameters, and honouring them now would
 * apply a filter with no control left to see or clear it — a threshold of 70
 * would return an empty list forever with nothing on screen explaining why. */

describe("filtersFromSearch", () => {
  it("ignores probability_min left over in an old link", () => {
    const f = filtersFromSearch(new URLSearchParams("probability_min=70&ticker=AAPL"));
    expect(f.probability_min).toBeUndefined();
    // and does not swallow the rest of the link while doing it
    expect(f.ticker).toBe("AAPL");
  });

  it("still reads the filters that remain", () => {
    const f = filtersFromSearch(
      new URLSearchParams("strength_min=80&tone=bull&rule_kind=macd_divergence"),
    );
    expect(f.strength_min).toBe(80);
    expect(f.tone).toBe("bull");
    // The honest way to select detectors, and the reason the probability
    // filter was redundant as well as misleading.
    expect(f.rule_kind).toBe("macd_divergence");
  });

  it("reads an empty query as no filters at all", () => {
    const f = filtersFromSearch(new URLSearchParams(""));
    expect(f.probability_min).toBeUndefined();
    expect(f.strength_min).toBeUndefined();
    expect(f.archived).toBe(false);
  });
});

/* ─── searchFromState: l'inverso, e la chiave che non e' sua ─────────────── */

describe("searchFromState", () => {
  const vuoti = {} as Parameters<typeof searchFromState>[0];

  it("⚠️ non tocca i parametri delle ALTRE schede", async () => {
    // Il difetto che questo chiude: la serializzazione ricostruiva la query da
    // zero, quindi il primo render della lista cancellava `vista` — e con essa
    // il filtro per tono e condizione della scheda «In formazione». Si
    // presenta come «la scheda non si apre», e si cerca ovunque tranne che in
    // un effetto di sincronizzazione.
    const correnti = new URLSearchParams("vista=segnali&tono=ribassisti&condizione=sr_flip");
    const out = searchFromState(vuoti, 0, "triggered_at", "desc", correnti);
    expect(out.get("vista")).toBe("segnali");
    expect(out.get("tono")).toBe("ribassisti");
    expect(out.get("condizione")).toBe("sr_flip");
  });

  it("le chiavi PROPRIE che tornano al default spariscono", async () => {
    // Controllo negativo del test sopra: se conservasse tutto, un filtro
    // tolto resterebbe nell'URL e un segnalibro riaprirebbe una lista
    // filtrata da un controllo che appare vuoto.
    const correnti = new URLSearchParams("ticker=AAPL&page=3&sort_dir=asc&vista=segnali");
    const out = searchFromState(vuoti, 0, "triggered_at", "desc", correnti);
    expect(out.get("ticker")).toBeNull();
    expect(out.get("page")).toBeNull();
    expect(out.get("sort_dir")).toBeNull();
    expect(out.get("vista")).toBe("segnali");
  });

  it("scrive solo i valori non di default, e la pagina e' 1-based", () => {
    const out = searchFromState(
      { ticker: "MSFT", archived: true }, 2, "ticker", "asc", new URLSearchParams(),
    );
    expect(out.get("ticker")).toBe("MSFT");
    expect(out.get("archived")).toBe("true");
    expect(out.get("page")).toBe("3");
    expect(out.get("sort_by")).toBe("ticker");
    expect(out.get("q")).toBeNull();
  });
});

/* ─── L'esito e' quasi tutto archiviato ───────────────────────────────────── */

describe("esitoNascostoDallArchivio", () => {
  it("vero quando si chiede un esito fra i soli segnali attivi", () => {
    // È la risposta a «perché gli azzeccati sono solo cinque»: un segnale
    // viene archiviato da solo appena l'esito matura, quindi il conteggio a
    // schermo misurava la regola di archiviazione e non il motore.
    expect(esitoNascostoDallArchivio({ outcome: "hit", archived: false })).toBe(true);
  });

  it("falso appena gli archiviati rientrano, o quando si guardano solo loro", () => {
    // Controllo negativo: senza, l'avviso resterebbe a schermo proprio dopo
    // averlo seguito — cioè accanto ai dati che dichiara mancanti.
    expect(
      esitoNascostoDallArchivio({ outcome: "hit", archived: false, include_archived: true }),
    ).toBe(false);
    expect(esitoNascostoDallArchivio({ outcome: "hit", archived: true })).toBe(false);
  });

  it("falso senza un filtro sull'esito", () => {
    // La lista senza filtro Esito è un'inbox, e un'inbox che mostra i vivi è
    // esattamente ciò che deve fare.
    expect(esitoNascostoDallArchivio({ archived: false })).toBe(false);
  });
});

describe("filtersFromSearch — entrambe le metà", () => {
  it("legge include_archived dall'URL e lo riscrive", () => {
    const f = filtersFromSearch(new URLSearchParams("outcome=hit&include_archived=true"));
    expect(f.include_archived).toBe(true);
    const out = searchFromState(f, 0, "triggered_at", "desc", new URLSearchParams());
    expect(out.get("include_archived")).toBe("true");
    expect(out.get("outcome")).toBe("hit");
  });

  it("⚠️ assente vuol dire assente, non false", () => {
    // `include_archived: false` e `undefined` viaggiano diversamente sul filo:
    // il client invia la chiave solo quando è vera, e scrivere `false`
    // nell'URL sporcherebbe ogni link con un default.
    const f = filtersFromSearch(new URLSearchParams("outcome=hit"));
    expect(f.include_archived).toBeUndefined();
    const out = searchFromState(f, 0, "triggered_at", "desc", new URLSearchParams());
    expect(out.has("include_archived")).toBe(false);
  });
});
