import { describe, expect, it } from "vitest";

import { queryScadute, QUERY_CRITICHE_HOME } from "./freschezzaHome";

const ORA = 1_000_000_000;
const stato = (eta: Record<string, number | undefined>) => (chiave: readonly unknown[]) => {
  const e = eta[chiave.join("/")];
  return e === undefined ? undefined : { dataUpdatedAt: ORA - e, data: {} };
};

describe("l'eta' massima dei dati della home (FA-179)", () => {
  it("un prezzo di tre giorni fa e' scaduto, un riepilogo di dieci minuti no", () => {
    const s = queryScadute(stato({ "live-assets": 3 * 86_400_000, "dashboard/summary": 10 * 60_000 }), ORA);
    expect(s.map((q) => q.chiave.join("/"))).toEqual(["live-assets"]);
  });

  it("un dato assente non e' «vecchio»: e' il primo caricamento", () => {
    expect(queryScadute(() => undefined, ORA)).toEqual([]);
  });

  it("le eta' massime sono quelle dichiarate", () => {
    const eta = Object.fromEntries(QUERY_CRITICHE_HOME.map((q) => [q.chiave.join("/"), q.etaMassimaMs]));
    expect(eta).toEqual({
      "live-assets": 120_000, "etoro/vivo": 120_000,
      "dashboard/summary": 900_000, "dashboard/market-summary": 900_000,
    });
  });

  it("se l'ultimo tentativo e' fallito il cancello si apre, invece di uno scheletro eterno", () => {
    const s = queryScadute(() => ({ dataUpdatedAt: ORA - 3 * 86_400_000, errorUpdatedAt: ORA - 1000, data: {} }), ORA);
    expect(s).toEqual([]);
  });
});
