import { defineConfig, devices } from "@playwright/test";

/* ─── Il gate che jsdom non puo' essere ───────────────────────────────────
 *
 * ⚠️ Non e' "piu' test": e' l'unico posto dove certi difetti sono VISIBILI.
 * jsdom non fa layout — `getBoundingClientRect` restituisce zeri — quindi
 * nessun test della suite vitest puo' vedere un traboccamento orizzontale, un
 * contrasto insufficiente, un focus invisibile o un bersaglio troppo piccolo
 * per un dito. CLAUDE.md lo dice gia' per axe; vale per tutta la classe.
 *
 * La prova: l'11 settembre 590 test erano verdi e OTTO rotte traboccavano su
 * un telefono, in produzione. Sono stati trovati a mano, misurando in un
 * browser vero. Questo file fa in modo che non serva rifarlo a mano.
 *
 * ⚠️ Tre viewport e non uno. L'audit unificato su 426 screenshot ha smentito
 * la tesi «il desktop e' il viewport peggiore»: contati correttamente, i
 * contenitori con scorrimento interno sono desktop 35 / tablet 31 / mobile 39,
 * e il peggiore cambia da pagina a pagina. Sorvegliarne uno solo sposta il
 * difetto, non lo toglie.
 */
export default defineConfig({
  testDir: "./e2e",
  // Un gate che fallisce a intermittenza viene disattivato: meglio lento.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  timeout: 45_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:8000",
    trace: "retain-on-failure",
    // Il service worker dell'app intercetta le richieste PRIMA di
    // `page.route`, quindi con lui attivo non si puo' servire axe dalla
    // stessa origine e la CSP `script-src 'self'` blocca ogni altra via.
    // Bloccarlo e' preferibile a spegnere la CSP: la CSP e' comportamento
    // reale che vogliamo attivo mentre misuriamo, il service worker e' una
    // cache che non cambia ne' layout ne' accessibilita'.
    serviceWorkers: "block",
    screenshot: "only-on-failure",
  },
  /* ⚠️ UN SOLO MOTORE, e va detto perche' nessuno creda il contrario.
   *
   * Tutti e tre i progetti girano su chromium: cambia il VIEWPORT e
   * l'emulazione tattile, non il motore di rendering. Quindi questo gate NON
   * copre le differenze di Safari/WebKit — un difetto che esiste solo li'
   * passerebbe verde.
   *
   * La scelta e' deliberata: `iPad Mini` di Playwright porta webkit con se',
   * che triplica il tempo di installazione dei browser in CI per una
   * copertura di motore su un'app a un utente. Se un giorno un difetto
   * WebKit dovesse presentarsi davvero, la correzione e' una riga
   * (`...devices["iPad Mini"]`) piu' `playwright install webkit` nel job —
   * non una riscrittura. Fino ad allora sarebbe costo senza evidenza. */
  projects: [
    {
      // 375x812 e' piu' stretto del 390x844 dell'audit: la soglia piu' dura
      // delle due, e gli otto difetti del 12 settembre sono stati misurati qui.
      name: "mobile",
      use: {
        ...devices["Pixel 7"],
        browserName: "chromium",
        viewport: { width: 375, height: 812 },
      },
    },
    {
      name: "tablet",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 768, height: 1024 },
        hasTouch: true,
        isMobile: false,
      },
    },
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
  ],
});
