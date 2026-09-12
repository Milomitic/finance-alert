import { ROTTE, expect, test } from "./fixtures";

/* ─── Traboccamento orizzontale: la classe che 590 test non potevano vedere ──
 *
 * ⚠️ Il controllo OVVIO non funziona in questa app, e va detto qui perche' il
 * prossimo lettore lo riscrivera' altrimenti. `html` e `body` sono
 * `overflow-x: clip` e `<main>` porta `overflow-y: auto`, che per specifica
 * CSS forza anche l'asse orizzontale ad `auto`. Quindi
 * `document.documentElement.scrollWidth` e' SEMPRE uguale a `clientWidth`,
 * anche mentre il contenuto esce dallo schermo: il traboccamento diventa una
 * barra dentro `<main>`, non a livello di documento.
 *
 * Il riquadro giusto e' quello di `<main>`. Il primo rilevatore scritto per
 * questa indagine ha risposto «zero difetti» su ogni rotta ed era falso.
 */

/** Misura eseguita NEL browser. Torna anche il primo colpevole, perche' un
 *  gate che dice solo «qualcosa e' largo» costa a chi lo deve riparare. */
async function traboccamento(page: import("@playwright/test").Page) {
  return page.evaluate(() => {
    const main = document.querySelector("main");
    if (!main) return { over: -1, colpevole: "nessun <main>", chars: 0 };
    const limite = main.getBoundingClientRect().left + main.clientWidth;
    const scorre = (e: Element) =>
      /(auto|scroll|hidden|clip)/.test(getComputedStyle(e).overflowX);
    const nascosto = (e: Element) => {
      const s = getComputedStyle(e);
      return s.display === "none" || s.visibility === "hidden" || s.opacity === "0";
    };
    const fuori: Element[] = [];
    for (const el of Array.from(main.querySelectorAll("*"))) {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height || r.right <= limite + 1 || nascosto(el)) continue;
      // Chi sta dentro un contenitore che scorre di proposito (una tabella in
      // `overflow-x-auto`) non e' un difetto: scorre, non sfonda.
      let p = el.parentElement, salta = false;
      while (p && p !== main) {
        if (scorre(p) || nascosto(p)) { salta = true; break; }
        p = p.parentElement;
      }
      if (!salta) fuori.push(el);
    }
    const esterni = fuori.filter((e) => !fuori.some((o) => o !== e && o.contains(e)));
    const primo = esterni[0];
    return {
      over: main.scrollWidth - main.clientWidth,
      chars: (main as HTMLElement).innerText.length,
      colpevole: primo
        ? `<${primo.tagName.toLowerCase()} class="${
            typeof primo.className === "string" ? primo.className.slice(0, 90) : ""
          }"> — "${(primo.textContent ?? "").trim().replace(/\s+/g, " ").slice(0, 45)}"`
        : "",
    };
  });
}

for (const rotta of ROTTE) {
  test(`${rotta.nome} (${rotta.path}) non esce dallo schermo`, async ({ page }) => {
    await page.goto(rotta.path, { waitUntil: "networkidle" });
    await page.waitForTimeout(1200); // code-splitting + prima passata di query

    const m = await traboccamento(page);

    /* ⚠️ IL PAVIMENTO VIENE PRIMA. Se la pagina e' vuota non puo' traboccare,
     * e un'asserzione di non-traboccamento su una pagina vuota e' vera di
     * niente. Questa riga e' cio' che rende falsificabile quella sotto. */
    expect(
      m.chars,
      `${rotta.path} ha reso ${m.chars} caratteri: sotto il pavimento di ` +
        `${rotta.minChars}. Il seme (app.scripts.seed_e2e) non ha funzionato, ` +
        `oppure la pagina e' rotta — in entrambi i casi il controllo sul ` +
        `layout qui sotto NON misurerebbe nulla.`,
    ).toBeGreaterThanOrEqual(rotta.minChars);

    expect(
      m.over,
      `${rotta.path} sborda di ${m.over}px oltre <main>. Primo colpevole: ${m.colpevole}`,
    ).toBeLessThanOrEqual(1);
  });
}

test("il rilevatore SA fallire", async ({ page }) => {
  /* ⚠️ Controllo negativo obbligatorio, e non e' cerimonia: la prima versione
   * di questa misura restituiva zero su ogni rotta perche' scartava l'intera
   * app come «contenitore che scorre». Un gate che non puo' fallire e' un
   * gate spento, e sarebbe indistinguibile da un gate che passa. */
  await page.goto("/", { waitUntil: "networkidle" });
  const prima = await traboccamento(page);
  expect(prima.over).toBeLessThanOrEqual(1);

  await page.evaluate(() => {
    const main = document.querySelector("main")!;
    const d = document.createElement("div");
    d.id = "sonda-traboccamento";
    /* ⚠️ RELATIVA alla larghezza di <main>, non un numero fisso. Una sonda da
     * 900px sborda su un telefono e NON su un desktop da 1440: scritta cosi'
     * il controllo negativo passava su mobile e falliva su desktop, cioe'
     * proprio dove serviva per dire che il rilevatore e' vivo. Il test ha
     * trovato il difetto nel test, che e' il suo mestiere. */
    d.style.cssText = `width:${main.clientWidth * 2}px;height:20px`;
    d.textContent = "SONDA";
    main.appendChild(d);
  });
  const dopo = await traboccamento(page);
  expect(dopo.over, "una sonda larga il doppio di <main> deve essere vista").toBeGreaterThan(100);
  expect(dopo.colpevole).toContain("SONDA");
});
