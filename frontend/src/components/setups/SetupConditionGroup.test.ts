import { describe, expect, it } from "vitest";

import type { Setup } from "@/hooks/useSetups";

import { columnsFor } from "./SetupConditionGroup";

/* Una colonna vuota per OGNI riga non va renderizzata.
 *
 * Alcune famiglie di condizione non hanno un livello di prezzo da
 * attraversare, quindi per quei gruppi «Livello d'innesco» e «Distanza»
 * mostravano un trattino su tutte le righe: due colonne che occupavano
 * larghezza per non dire nulla, su una tabella che gia tagliava «Attesa» a
 * destra.
 *
 * ⚠️ Ma un trattino NON e sempre uno spreco. Su una riga singola dice
 * "questo innesco non e un attraversamento di prezzo", che e una vera
 * informazione — la stessa distinzione fra assenza e zero che questo repo
 * applica ovunque. La colonna sparisce solo quando NESSUNA riga del gruppo la
 * riempie: nascondere una colonna perche' una riga non la riempie sarebbe il
 * difetto opposto, e i test sotto lo fissano in entrambe le direzioni.
 */

let seq = 0;

function setup(over: Partial<Setup> = {}): Setup {
  seq += 1;
  return {
    id: seq,
    stock_id: seq,
    ticker: `T${seq}`,
    name: `Titolo ${seq}`,
    detector: "trend_pullback",
    tone: "bull",
    convenience: 70,
    proximity: 0.8,
    missing: "—",
    status: "forming",
    first_seen_at: "2026-09-01T00:00:00Z",
    last_seen_at: "2026-09-10T00:00:00Z",
    distance_atr: null,
    annotations: null,
    ...over,
  } as unknown as Setup;
}

const withLevel = () =>
  setup({ annotations: { levels: [{ label: "EMA20", price: 12.3 }] } } as Partial<Setup>);

describe("una colonna resta se almeno una riga la riempie", () => {
  it("basta un setup con il livello a tenere la colonna", () => {
    const c = columnsFor([setup(), withLevel(), setup()]);

    expect(c.level).toBe(true);
  });

  it("basta un setup con la distanza a tenere la sua", () => {
    const c = columnsFor([setup(), setup({ distance_atr: 0.4 }), setup()]);

    expect(c.distance).toBe(true);
  });
});

describe("una colonna sparisce solo se nessuna riga la riempie", () => {
  it("un gruppo senza livelli perde la colonna del livello", () => {
    const c = columnsFor([setup(), setup(), setup()]);

    expect(c.level).toBe(false);
  });

  it("e senza distanze perde anche quella", () => {
    const c = columnsFor([setup(), setup()]);

    expect(c.distance).toBe(false);
  });

  it("le due decisioni sono indipendenti", () => {
    // Il controllo negativo: una implementazione che le legasse insieme
    // passerebbe tutti i test sopra.
    const c = columnsFor([setup({ distance_atr: 1.2 })]);

    expect(c.distance).toBe(true);
    expect(c.level).toBe(false);
  });
});

describe("il template della griglia e sempre una stringa letterale", () => {
  it.each([
    [[withLevel()], "132px"],
    [[setup({ distance_atr: 0.4 })], "92px"],
  ])("la colonna presente ha la sua larghezza", (setups, width) => {
    expect(columnsFor(setups as Setup[]).cols).toContain(width);
  });

  it("le larghezze assenti non compaiono nel template", () => {
    // ⚠️ Il purger di Tailwind legge SOLO stringhe letterali: comporre
    // `sm:grid-cols-[${...}]` a runtime produrrebbe una classe che il bundle
    // di produzione non contiene, e il difetto sarebbe invisibile in
    // sviluppo. Le quattro combinazioni sono quindi scritte per esteso, e
    // questo test verifica che si scelga fra loro invece di costruirle.
    const c = columnsFor([setup()]);

    expect(c.cols).not.toContain("132px");
    expect(c.cols).not.toContain("92px");
    // La priorita e l'attesa non sono opzionali: ci sono sempre.
    expect(c.cols).toContain("88px");
    expect(c.cols).toContain("64px");
  });
});
