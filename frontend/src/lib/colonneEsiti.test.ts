import { describe, expect, it } from "vitest";

import {
  COLONNE_ESITI, COLONNE_ESITI_NASCONDIBILI, ordineDa, trackEsiti, versoIniziale,
  type ColonnaEsitiId,
} from "./colonneEsiti";

const tutte = () => true;

describe("trackEsiti", () => {
  it("con tutte le colonne riproduce i quattro template di prima", () => {
    // I template letterali che la lista usava fino al 2026-09-22: se la
    // configurazione li cambiasse, cambierebbe il layout senza che nessuno
    // l'abbia chiesto.
    expect(trackEsiti(tutte)).toEqual({
      "--g": "minmax(0,1fr) auto auto auto 64px",
      "--g-sm": "minmax(0,1fr) 116px 68px 60px 64px 96px",
      "--g-lg": "minmax(0,1fr) 116px 68px 60px 64px 96px 112px",
      "--g-xl": "minmax(0,1fr) 136px 116px 68px 60px 64px 60px 120px 112px",
    });
  });

  it("⚠️ una colonna nascosta toglie la SUA traccia a ogni larghezza", () => {
    const senzaPL = (id: ColonnaEsitiId) => id !== "pl";
    const g = trackEsiti(senzaPL);
    expect(g["--g"]).toBe("minmax(0,1fr) auto auto 64px");
    expect(g["--g-xl"]).toBe("minmax(0,1fr) 136px 116px 68px 64px 60px 120px 112px");
  });

  it("il titolo resta anche se qualcuno prova a spegnerlo", () => {
    const g = trackEsiti(() => false);
    for (const v of Object.values(g)) expect(v).toBe("minmax(0,1fr)");
  });
});

describe("le colonne come dato", () => {
  it("il menu offre tutte le colonne tranne il titolo", () => {
    expect(COLONNE_ESITI_NASCONDIBILI.map((c) => c.id)).not.toContain("titolo");
    expect(COLONNE_ESITI_NASCONDIBILI).toHaveLength(COLONNE_ESITI.length - 1);
  });

  it("gli ordinamenti sono quelli che il server accetta", () => {
    // Specchio di `ORDINAMENTI_ESITI` nel backend: un nome qui che il server
    // non conosce sarebbe un 400 al primo clic.
    const chiavi = COLONNE_ESITI.map((c) => c.ordina).filter(Boolean).sort();
    expect(chiavi).toEqual(
      ["bars_to_outcome", "detector", "esito", "pl", "r_multiple", "resolved_date", "ticker"],
    );
  });

  it("parole dall'A, numeri e date dal piu' grande", () => {
    expect(versoIniziale("ticker")).toBe("asc");
    expect(versoIniziale("r_multiple")).toBe("desc");
    expect(versoIniziale("resolved_date")).toBe("desc");
  });

  it("un ordinamento sconosciuto nell'URL non passa", () => {
    expect(ordineDa("pl")).toBe("pl");
    expect(ordineDa("forza")).toBeNull();
    expect(ordineDa(null)).toBeNull();
  });
});
