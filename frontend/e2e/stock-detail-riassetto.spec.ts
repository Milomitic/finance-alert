import { expect, test } from "./fixtures";

/* ─── Il riassetto oltre il Full HD, misurato dove esiste ─────────────────
 *
 * Oltre i 1920px la pagina dettaglio titolo cambia DISPOSIZIONE, non solo
 * dimensioni: il profilo societa' si monta dentro l'intestazione (sopra lo
 * sparkline), le due schede di score si affiancano e i segnali scendono sotto.
 *
 * ⚠️ Nessun altro presidio puo' vederlo.
 *   - vitest/jsdom non fa layout: `getBoundingClientRect` torna zeri, quindi
 *     «affiancate» e «sotto» non sono nemmeno esprimibili;
 *   - i test unitari vedono i pezzi (l'intestazione accetta uno slot, il
 *     profilo sa togliersi la cornice) e nessuno vede la PAGINA;
 *   - gli altri tre viewport del gate — 375, 768, 1440 — sono TUTTI sotto la
 *     soglia, cioe' misurano esclusivamente il ramo vecchio.
 *
 * ⚠️ Il test piu' importante e' il conteggio dei profili. Il ramo e' scritto
 * in JS invece che con `hidden` proprio per non montarne due; una regressione
 * che torna alle classi sarebbe INVISIBILE a occhio — la copia di troppo e'
 * nascosta — e costerebbe una query in piu' per apertura di pagina piu' un
 * doppione letto dagli assistivi. Solo un conteggio lo vede.
 */

const TITOLO = "/stocks/AAPL";

type Riquadro = { x: number; y: number; w: number; h: number };
type Misura = {
  profili: number;
  profiloNellIntestazione: boolean | null;
  intestazioneTrovata: boolean;
  score: Riquadro | null;
  tecnico: Riquadro | null;
  segnali: Riquadro | null;
  setupsPresente: boolean;
};

async function disposizione(page: import("@playwright/test").Page): Promise<Misura> {
  return page.evaluate(() => {
    const foglie = () =>
      Array.from(document.querySelectorAll("main *")).filter((e) => e.children.length === 0);
    const conTesto = (t: string) =>
      foglie().find((e) => (e.textContent ?? "").trim().startsWith(t)) ?? null;
    const scheda = (e: Element | null) => e?.closest("[data-card]") ?? null;
    const riquadro = (e: Element | null) => {
      if (!e) return null;
      const r = e.getBoundingClientRect();
      return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
    };

    /* L'intestazione si riconosce dallo sparkline, non dal ticker: il ticker
     * compare anche altrove nella pagina, lo sparkline a tutta scheda no. */
    const spark = document.querySelector<SVGElement>(
      'main [data-card] svg[preserveAspectRatio="none"]',
    );
    const intestazione = spark ? spark.closest("[data-card]") : null;

    const profili = foglie().filter((e) => (e.textContent ?? "").trim() === "Profilo società");

    return {
      profili: profili.length,
      profiloNellIntestazione:
        profili.length && intestazione ? scheda(profili[0]) === intestazione : null,
      intestazioneTrovata: !!intestazione,
      score: riquadro(scheda(conTesto("Stock score"))),
      tecnico: riquadro(scheda(conTesto("Valutazione tecnica"))),
      segnali: riquadro(scheda(conTesto("Segnali storici per questo ticker"))),
      setupsPresente: !!conTesto("In formazione su questo titolo"),
    };
  });
}

async function apri(page: import("@playwright/test").Page) {
  await page.goto(TITOLO, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500); // code-splitting + prima passata di query
  const m = await disposizione(page);
  /* Il pavimento, prima di ogni geometria: su una pagina che non ha reso
   * niente, «le schede sono affiancate» sarebbe vero di due riquadri
   * inesistenti — la forma che CLAUDE.md registra quattro volte. */
  expect(m.intestazioneTrovata, "intestazione non trovata: la pagina non ha reso").toBe(true);
  expect(m.score, "la scheda Stock score non e' stata resa").not.toBeNull();
  expect(m.tecnico, "la scheda Valutazione tecnica non e' stata resa").not.toBeNull();
  return m;
}

test.describe("dettaglio titolo — riassetto oltre il Full HD", () => {
  test("oltre il Full HD: score affiancati, profilo nell'intestazione, segnali sotto", async ({
    page,
  }, info) => {
    test.skip(info.project.name !== "over-fhd", "misura il ramo oltre 1920px");
    const m = await apri(page);

    // 1. Le due schede di score condividono la riga.
    expect(
      Math.abs(m.score!.y - m.tecnico!.y),
      `score e tecnico non sono sulla stessa riga: y=${m.score!.y} contro ${m.tecnico!.y}`,
    ).toBeLessThanOrEqual(8);
    expect(m.score!.x, "score e tecnico sono nella stessa colonna").not.toBe(m.tecnico!.x);

    // 2. Il profilo e' UNO SOLO, ed e' dentro l'intestazione.
    expect(m.profili, "il profilo e' montato piu' di una volta").toBe(1);
    expect(m.profiloNellIntestazione, "il profilo non e' dentro l'intestazione").toBe(true);

    // 3. I segnali stanno sotto entrambe le schede di score.
    expect(m.segnali, "la scheda dei segnali non e' stata resa").not.toBeNull();
    const fondoScore = Math.max(m.score!.y + m.score!.h, m.tecnico!.y + m.tecnico!.h);
    expect(
      m.segnali!.y,
      `i segnali non sono sotto gli score: y=${m.segnali!.y}, fondo score=${fondoScore}`,
    ).toBeGreaterThanOrEqual(fondoScore);

    // 4. La scheda «In formazione» e' stata rimossa su richiesta.
    expect(m.setupsPresente, "la scheda «In formazione su questo titolo» e' tornata").toBe(false);
  });

  test("fino al Full HD: score impilati e profilo in una riga sua", async ({ page }, info) => {
    /* ⚠️ Il controllo negativo, e senza di esso il test sopra passerebbe anche
     * con una pagina che si dispone COSI' a ogni larghezza — cioe' senza
     * riassetto affatto, avendo solo rotto il layout a 1440px. */
    test.skip(info.project.name !== "desktop", "misura il ramo fino a 1920px");
    const m = await apri(page);

    expect(
      m.score!.x,
      `a 1440px score e tecnico devono restare impilati, non affiancati`,
    ).toBe(m.tecnico!.x);
    expect(m.score!.y).not.toBe(m.tecnico!.y);
    expect(m.profili, "il profilo e' montato piu' di una volta").toBe(1);
    expect(
      m.profiloNellIntestazione,
      "a 1440px il profilo deve avere una riga sua, non stare nell'intestazione",
    ).toBe(false);
    expect(m.setupsPresente).toBe(false);
  });
});
