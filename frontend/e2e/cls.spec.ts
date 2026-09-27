import { writeFileSync } from "node:fs";

import type { Page } from "@playwright/test";

import { ROTTE, expect, test } from "./fixtures";

/* ─── La stabilita' del layout, misurata dove jsdom non puo' (FA-106) ─────
 *
 * RUM in produzione (2026-09-26, pochi campioni): CLS p75 0,98 sul dettaglio
 * titolo e 0,19 sul cruscotto, contro la soglia «buono» di 0,1. Nessun presidio
 * lo vedeva: jsdom non fa layout, e il gate misurava traboccamento e
 * accessibilita' su una pagina gia' ferma.
 *
 * Il CLS e' quello di web-vitals: la PEGGIORE finestra di sessione, cioe'
 * scosse a meno di un secondo l'una dall'altra in una finestra di al massimo
 * cinque, escluse quelle subito dopo un input. Si misura il CARICAMENTO — dalla
 * navigazione a pagina ferma — che e' dove i dati arrivano e spostano cio' che
 * e' gia' a schermo.
 *
 * Il tetto e' UNO per tutte le rotte e i viewport: la soglia «buono» di
 * web-vitals. Misurato prima di accenderlo (2026-09-28, seme e2e): tutte le
 * rotte fra 0 e 0,044 dopo le correzioni, contro 0,11-0,62 prima. Le cause,
 * sempre della stessa famiglia — un blocco che arriva coi dati e spinge giu'
 * cio' che c'e' gia':
 *
 *   - lo scheletro trasformato nella pagina da React (stessa radice, stesso
 *     `<div>` nella stessa posizione): dettaglio titolo, esplora;
 *   - il log disegnato subito e spinto giu' dallo snapshot: diagnostica;
 *   - sezioni che caricano ognuna per conto suo sopra scheletri piu' bassi:
 *     superinvestor, in formazione, segnali — ora il primo caricamento e' un
 *     blocco solo;
 *   - il riquadro VIX e la riga di contesto del jumbotron, nati vuoti.
 *
 * ⚠️ Il seme non ha rete: quotazioni, notizie e fondamentali falliscono
 * subito. Una scossa che nasce solo coi dati veri — una scheda che si allunga
 * quando arrivano le notizie — qui NON si vede. Il RUM in produzione resta la
 * misura di quella meta'.
 */

const TETTO = 0.1;

type Scossa = { valore: number; t: number; chi: string[] };
type Misura = { cls: number; scosse: Scossa[] };

declare global {
  interface Window {
    __cls?: Misura & { sessione: number; prima: number; ultima: number };
  }
}

/** Installato PRIMA della navigazione: le scosse del primo disegno contano. */
async function osserva(page: Page) {
  await page.addInitScript(() => {
    const stato = { cls: 0, sessione: 0, prima: 0, ultima: 0, scosse: [] as Scossa[] };
    window.__cls = stato;
    // Il colpevole si NOMINA: un numero senza l'elemento che si e' mosso fa
    // cercare a caso (CLAUDE.md, «un cancello deve nominare il colpevole»).
    const nome = (n: Node | null | undefined) => {
      if (!(n instanceof Element)) return "(testo)";
      const classi = typeof n.className === "string"
        ? n.className.split(/\s+/).filter(Boolean).slice(0, 4).join(".")
        : "";
      const testo = (n.textContent ?? "").trim().replace(/\s+/g, " ").slice(0, 40);
      return `${n.tagName.toLowerCase()}${classi ? "." + classi : ""} «${testo}»`;
    };
    // Da dove a dove: senza la direzione e la distanza non si distingue un
    // blocco spinto giu' da qualcosa sopra da una colonna che si allarga.
    const tratta = (s: { previousRect: DOMRectReadOnly; currentRect: DOMRectReadOnly }) =>
      `(${Math.round(s.previousRect.x)},${Math.round(s.previousRect.y)})` +
      `->(${Math.round(s.currentRect.x)},${Math.round(s.currentRect.y)})`;
    new PerformanceObserver((lista) => {
      for (const e of lista.getEntries() as unknown as {
        value: number; startTime: number; hadRecentInput: boolean;
        sources?: { node?: Node | null; previousRect: DOMRectReadOnly; currentRect: DOMRectReadOnly }[];
      }[]) {
        if (e.hadRecentInput) continue;
        if (stato.sessione && e.startTime - stato.ultima < 1000 && e.startTime - stato.prima < 5000) {
          stato.sessione += e.value;
          stato.ultima = e.startTime;
        } else {
          stato.sessione = e.value;
          stato.prima = stato.ultima = e.startTime;
        }
        stato.cls = Math.max(stato.cls, stato.sessione);
        stato.scosse.push({
          valore: e.value, t: Math.round(e.startTime),
          chi: (e.sources ?? []).map((s) => `${nome(s.node)} ${tratta(s)}`),
        });
      }
    }).observe({ type: "layout-shift", buffered: true });
  });
}

const raccolto: Record<string, Record<string, Misura>> = {};

for (const rotta of ROTTE) {
  test(`${rotta.nome} (${rotta.path}) non salta mentre carica`, async ({ page }, info) => {
    await osserva(page);
    await page.goto(rotta.path, { waitUntil: "networkidle" });
    // Code-splitting, prima passata di query e le risposte lente: il CLS si
    // legge a pagina FERMA, non al primo disegno.
    await page.waitForTimeout(2500);

    const caratteri = await page.evaluate(
      () => (document.querySelector("main") as HTMLElement | null)?.innerText.length ?? 0,
    );
    expect(caratteri, `${rotta.path} e' vuota: il CLS di una pagina vuota e' zero per costruzione`)
      .toBeGreaterThanOrEqual(rotta.minChars);

    const m = await page.evaluate(() => ({ cls: window.__cls!.cls, scosse: window.__cls!.scosse }));
    (raccolto[info.project.name] ??= {})[rotta.path] = m;
    const peggiori = [...m.scosse].sort((a, b) => b.valore - a.valore).slice(0, 4)
      .map((s) => `${s.valore.toFixed(3)} a ${s.t}ms: ${s.chi.join(" | ")}`);
    console.log(`CLS ${info.project.name} ${rotta.path}: ${m.cls.toFixed(3)}\n  ${peggiori.join("\n  ")}`);
    expect(
      m.cls,
      `${rotta.path} salta mentre carica: CLS ${m.cls.toFixed(3)} oltre ${TETTO}. ` +
        `Le scosse piu' grandi, con l'elemento spostato e da dove a dove:\n  ${peggiori.join("\n  ")}`,
    ).toBeLessThanOrEqual(TETTO);
  });
}

test("il misuratore SA vedere una scossa", async ({ page }) => {
  /* Controllo negativo: senza, un osservatore rotto — un tipo di voce
   * sbagliato, un `buffered` dimenticato — renderebbe verde ogni rotta per
   * costruzione. Un blocco inserito in cima a <main> a pagina ferma, senza
   * input, sposta tutto cio' che c'e' sotto: deve contare. */
  await osserva(page);
  await page.goto("/positions", { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  const prima = await page.evaluate(() => window.__cls!.cls);
  expect(prima).toBeLessThanOrEqual(TETTO);

  await page.evaluate(() => {
    const main = document.querySelector("main")!;
    const sonda = document.createElement("div");
    sonda.style.height = `${Math.round(window.innerHeight / 2)}px`;
    sonda.textContent = "SONDA";
    main.prepend(sonda);
  });
  await page.waitForTimeout(500);
  const dopo = await page.evaluate(() => window.__cls!.cls);
  expect(dopo, "una sonda alta mezzo schermo in cima a <main> deve produrre una scossa")
    .toBeGreaterThan(TETTO);
});

test.afterAll(async ({}, info) => {
  const file = process.env.E2E_CLS_OUT;
  if (!file || !raccolto[info.project.name]) return;
  writeFileSync(`${file}.${info.project.name}.json`, JSON.stringify(raccolto[info.project.name], null, 2));
});
