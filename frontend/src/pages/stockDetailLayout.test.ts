import { describe, expect, it } from "vitest";

import { OVER_FHD_PX } from "./StockDetailPage";

/* ─── Le DUE soglie di «oltre il Full HD» devono coincidere ───────────────
 *
 * Il riassetto della pagina dettaglio e' fatto per meta' in CSS e per meta' in
 * JS, e non per pigrizia:
 *
 *   CSS (`over-fhd:grid-cols-2`)  le due schede di score si affiancano
 *   JS  (`OVER_FHD_PX`)           il profilo si sposta DENTRO l'intestazione
 *                                 e i segnali scendono sotto gli score
 *
 * La seconda meta' non puo' essere CSS: cambia CHI sta DOVE, non come appare.
 * Con le classi il profilo resterebbe montato due volte — due query, due
 * alberi — e la copia nascosta verrebbe comunque misurata e letta dagli
 * assistivi.
 *
 * ⚠️ Due soglie separate divergono in silenzio. A quel punto esiste una banda
 * di larghezze in cui il profilo e' gia' salito nell'intestazione e gli score
 * sono ancora impilati: l'intestazione raddoppia di altezza accanto a una
 * colonna stretta, cioe' il peggio delle due disposizioni. Non lo vedrebbe
 * nessun test comportamentale, perche' jsdom non fa layout e il gate e2e
 * misura 375/768/1440 — tutte e tre SOTTO la soglia.
 */

const CONFIG = import.meta.glob("/tailwind.config.js", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

describe("soglia over-FHD", () => {
  it("il file di configurazione viene letto davvero", () => {
    /* Il pavimento: senza, l'asserzione sotto sarebbe vera di un file vuoto. */
    const testo = Object.values(CONFIG)[0] ?? "";
    expect(testo.length).toBeGreaterThan(200);
    expect(testo).toContain("screens");
  });

  it("il breakpoint Tailwind vale esattamente OVER_FHD_PX", () => {
    const testo = Object.values(CONFIG)[0] ?? "";
    const m = /['"]over-fhd['"]\s*:\s*['"](\d+)px['"]/.exec(testo);
    expect(m, "il breakpoint `over-fhd` non esiste piu' in tailwind.config.js")
      .not.toBeNull();
    expect(Number(m![1])).toBe(OVER_FHD_PX);
  });

  it("e' OLTRE il Full HD, non a Full HD", () => {
    /* 1920 netti e' ANCORA Full HD, e a quella larghezza la colonna destra
     * vale ~620px: divisa in due sono ~300px per scheda, sotto i ~410px su
     * cui e' stata decisa l'affiancatura. */
    expect(OVER_FHD_PX).toBeGreaterThan(1920);
  });
});
