import { ROTTE, expect, test } from "./fixtures";

import LINEA_BASE from "./a11y-baseline.json" with { type: "json" };

const AXE = "node_modules/axe-core/axe.min.js";

/* ─── Le violazioni che jsdom NON PUO' vedere ─────────────────────────────
 *
 * CLAUDE.md lo dice gia' della suite axe dentro vitest: «jsdom non carica alcun
 * foglio di stile, quindi un'intera classe di difetti reali e' invisibile —
 * contrasto, dimensione dei bersagli, visibilita' del focus». Due dei quattro
 * difetti trovati a mano il 9 settembre 2026 non potevano essere intercettati
 * da quella suite. Qui gli stili sono calcolati davvero.
 *
 * ⚠️ PERCHE' UNA LINEA DI BASE E NON UNO ZERO. La prima misura su questa app
 * ha trovato violazioni vere e PREESISTENTI: 53 combobox Radix senza nome
 * accessibile su /alerts, 12 righe role="button" che ne contengono altre,
 * contrasto insufficiente su /calendar e /sectors. Sono difetti reali e nessuno
 * e' stato introdotto dal gate. Gatare a zero significherebbe nascere rossi, e
 * un cancello che nasce rosso si impara a ignorare — che e' il modo in cui
 * smette di esistere pur restando nel file. E' la stessa barra che
 * eslint.hooks.config.js si e' data: una regola entra solo dopo la misura.
 *
 * Il contratto e' quindi il CRICCHETTO: il conteggio non puo' CRESCERE. Una
 * regola assente dalla linea di base deve restare a zero; una presente non
 * puo' peggiorare. Quando cala, il test lo dice e la linea va stretta.
 *
 * Per rigenerarla DOPO una correzione:  E2E_UPDATE_BASELINE=1 npm run e2e
 */

type Conteggi = Record<string, number>;
const BASE = LINEA_BASE as { rotte: Record<string, Conteggi> };

const BASE_PERCHE =
  "Arretrato MISURATO di accessibilita', non un obiettivo. Il gate impedisce " +
  "che cresca; non pretende che sia zero, perche' un cancello che nasce rosso " +
  "viene disattivato. Rigenerare con E2E_UPDATE_BASELINE=1 npm run e2e, e solo " +
  "dopo aver CORRETTO qualcosa - mai per far passare la CI.";

/** Inietta axe SENZA spegnere la CSP dell'app.
 *
 * ⚠️ addScriptTag da solo viene BLOCCATO: l'app serve script-src 'self' e un
 * tag inline non e' 'self'. La prima stesura falliva cosi' su tutte e dieci le
 * rotte, e senza il controllo negativo in fondo al file la diagnosi sarebbe
 * stata «l'app ha dieci problemi di accessibilita'» invece di «lo scanner non
 * e' mai partito».
 *
 * ⚠️ La scorciatoia sarebbe bypassCSP: true. Non si usa: la CSP e'
 * comportamento REALE dell'app, e misurare con la CSP spenta significa
 * misurare una pagina che nessun utente vede. Qui si intercetta una URL della
 * stessa origine — per il browser e' 'self', la CSP resta accesa. Il service
 * worker e' bloccato dalla configurazione, altrimenti intercetterebbe la
 * richiesta prima di page.route. */
async function violazioni(page: import("@playwright/test").Page): Promise<Conteggi> {
  await page.route("**/__e2e-axe.js", (rotta) =>
    // `path` fa leggere il file a Playwright: niente node:fs, quindi niente
    // @types/node - che CLAUDE.md vieta per il rischio sul lockfile.
    rotta.fulfill({ status: 200, contentType: "application/javascript", path: AXE }),
  );
  await page.addScriptTag({ url: "/__e2e-axe.js" });
  return page.evaluate(async () => {
    // @ts-expect-error axe e' iniettato a runtime
    const res = await window.axe.run(document, { resultTypes: ["violations"] });
    const out: Record<string, number> = {};
    for (const v of res.violations) out[v.id] = v.nodes.length;
    return out;
  });
}

const AGGIORNA = !!process.env.E2E_UPDATE_BASELINE;
const raccolto: Record<string, Conteggi> = {};

for (const rotta of ROTTE) {
  test(`${rotta.nome} - nessuna NUOVA violazione con stili veri`, async ({ page }, info) => {
    test.skip(info.project.name !== "desktop", "una misura basta: axe non dipende dal viewport");
    await page.goto(rotta.path, { waitUntil: "networkidle" });
    await page.waitForTimeout(1000);

    const caratteri = await page.evaluate(
      () => (document.querySelector("main") as HTMLElement | null)?.innerText.length ?? 0,
    );
    /* ⚠️ Il pavimento viene PRIMA, come nel gate di layout: axe su una pagina
     * vuota non trova niente e lo fa sembrare un successo. */
    expect(caratteri, `${rotta.path} e' vuota: axe non misurerebbe nulla`)
      .toBeGreaterThanOrEqual(rotta.minChars);

    const trovate = await violazioni(page);
    raccolto[rotta.path] = trovate;
    if (AGGIORNA) return;

    const attese = BASE.rotte[rotta.path] ?? {};
    const cresciute = Object.entries(trovate)
      .filter(([id, n]) => n > (attese[id] ?? 0))
      .map(([id, n]) => `${id}: ${attese[id] ?? 0} -> ${n}`);
    const calate = Object.entries(attese)
      .filter(([id, n]) => (trovate[id] ?? 0) < n)
      .map(([id, n]) => `${id}: ${n} -> ${trovate[id] ?? 0}`);

    if (calate.length) {
      console.log(
        `\n  v ${rotta.path} e' MIGLIORATA (${calate.join(", ")}).` +
          ` Stringi la linea di base: E2E_UPDATE_BASELINE=1 npm run e2e\n`,
      );
    }
    expect(
      cresciute,
      `${rotta.path}: nuove violazioni di accessibilita'. ${cresciute.join(" | ")}`,
    ).toEqual([]);
  });
}

test("la linea di base non e' vuota", async ({}, info) => {
  test.skip(info.project.name !== "desktop");
  /* ⚠️ Senza questo, svuotare il file renderebbe ogni asserzione sopra vera di
   * niente - e sarebbe anche il modo piu' rapido di «far passare la CI». Il
   * totale e' un arretrato reale e cala soltanto correggendo. */
  const totale = Object.values(BASE.rotte).reduce(
    (n, r) => n + Object.values(r).reduce((a, b) => a + b, 0),
    0,
  );
  expect(totale).toBeGreaterThan(20);
});

test("axe SA trovare una violazione", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop");
  /* Controllo negativo, e qui NON e' cerimonia: la prima stesura falliva su
   * dieci rotte perche' la CSP bloccava l'iniezione, cioe' lo scanner non
   * girava affatto. E' questo test che l'ha detto. */
  await page.goto("/", { waitUntil: "networkidle" });
  await page.evaluate(() => {
    const b = document.createElement("button");
    b.id = "sonda-a11y";
    // Un bottone il cui unico contenuto e' un'icona nascosta agli assistivi:
    // per axe non ha nome accessibile. Costruito con metodi DOM, non innerHTML.
    const icona = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    icona.setAttribute("aria-hidden", "true");
    icona.setAttribute("width", "10");
    icona.setAttribute("height", "10");
    b.appendChild(icona);
    document.querySelector("main")!.prepend(b);
  });
  const trovate = await violazioni(page);
  expect(
    trovate["button-name"] ?? 0,
    "axe deve vedere un bottone senza nome accessibile",
  ).toBeGreaterThan(BASE.rotte["/"]?.["button-name"] ?? 0);
});

test("mobile - i bersagli tattili dei CONTROLLI sono raggiungibili", async ({ page }, info) => {
  test.skip(info.project.name !== "mobile", "vale solo sul viewport tattile");
  await page.goto("/alerts", { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);

  const piccoli = await page.evaluate(() => {
    // WCAG 2.2 SC 2.5.8 «Target Size (Minimum)»: 24x24 CSS px.
    const MIN = 24;
    const fuori: string[] = [];
    const main = document.querySelector("main");
    if (!main) return fuori;
    /* ⚠️ Solo CONTROLLI, non i link. I ticker dentro le tabelle sono link di
     * testo alti 19px: la norma stessa esenta i link in linea nel flusso del
     * testo, e ingrandirli vorrebbe dire ridisegnare la densita' di ogni
     * tabella dell'app. Sono un arretrato DICHIARATO, non una svista - ed e'
     * la ragione per cui questo gate puo' stare a ZERO senza mentire. */
    for (const el of Array.from(
      main.querySelectorAll("button, [role=button], input, select"),
    )) {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      const s = getComputedStyle(el);
      if (s.display === "none" || s.visibility === "hidden") continue;
      if (r.width >= MIN && r.height >= MIN) continue;

      /* ⚠️ L'ECCEZIONE DI SPAZIATURA, che la norma prevede esplicitamente.
       *
       * WCAG 2.2 SC 2.5.8 non chiede 24x24 in assoluto: un bersaglio piu'
       * piccolo e' CONFORME se un cerchio di 24px centrato su di esso non ne
       * interseca un altro. Il senso e' fisico — un dito impreciso fa danno
       * solo quando accanto c'e' qualcos'altro da colpire per sbaglio.
       *
       * Serve perche' le caselle di selezione di questa app sono 16px dentro
       * righe di tabella. ⚠️ Un primo tentativo le allargava con uno
       * pseudo-elemento `before:`; Tailwind non ha generato quelle classi (zero
       * regole nel CSS prodotto — la trappola del purger che CLAUDE.md gia'
       * registra) e la correzione era inerte mentre il commento accanto
       * dichiarava il contrario. Rimossa: meglio la norma applicata per intero
       * che una finta correzione con una bella spiegazione.
       *
       * Cosi' il gate resta severo dove conta: due controlli piccoli e vicini
       * falliscono ancora, ed e' il caso in cui si sbaglia bersaglio davvero. */
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const vicini = Array.from(
        main.querySelectorAll("button, [role=button], input, select, a[href]"),
      ).filter((altro) => {
        if (altro === el) return false;
        const ar = altro.getBoundingClientRect();
        if (!ar.width || !ar.height) return false;
        const acx = ar.left + ar.width / 2;
        const acy = ar.top + ar.height / 2;
        return Math.hypot(acx - cx, acy - cy) < MIN;
      });
      if (vicini.length === 0) continue;   // isolato: conforme per spaziatura

      fuori.push(
        `${el.tagName.toLowerCase()} ${Math.round(r.width)}x${Math.round(r.height)} ` +
          `"${(el.getAttribute("aria-label") || el.textContent || "").trim().slice(0, 28)}"`,
      );
    }
    return fuori;
  });

  expect(piccoli, `bersagli sotto 24x24 su un telefono: ${piccoli.join(" | ")}`).toEqual([]);
});

test("il focus da tastiera si VEDE", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop");
  /* jsdom non puo' rispondere: serve uno stile calcolato. Un focus invisibile
   * rende l'app inutilizzabile da tastiera pur passando ogni test strutturale. */
  await page.goto("/", { waitUntil: "networkidle" });
  const invisibili: string[] = [];
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press("Tab");
    const esito = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body) return null;
      const s = getComputedStyle(el);
      return {
        ok:
          (s.outlineStyle !== "none" && parseFloat(s.outlineWidth) > 0) ||
          (s.boxShadow !== "none" && s.boxShadow !== ""),
        chi: `${el.tagName.toLowerCase()}.${(el.className || "").toString().slice(0, 40)}`,
      };
    });
    if (esito && !esito.ok) invisibili.push(esito.chi);
  }
  expect(invisibili, `ricevono il focus senza mostrarlo: ${invisibili.join(", ")}`).toEqual([]);
});

test.afterAll(async () => {
  if (!AGGIORNA || !Object.keys(raccolto).length) return;
  const fs = await import("node:fs");
  fs.writeFileSync(
    "e2e/a11y-baseline.json",
    JSON.stringify({ _perche: BASE_PERCHE, rotte: raccolto }, null, 2) + "\n",
    "utf-8",
  );
  console.log(`\nlinea di base riscritta su ${Object.keys(raccolto).length} rotte\n`);
});
