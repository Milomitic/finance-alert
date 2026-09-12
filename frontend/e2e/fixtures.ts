import { test as base, type Page } from "@playwright/test";

/* Sessione: il token e' MINTATO dal firmatario dell'app e passato per env.
 *
 * ⚠️ Non passa mai per il repository ne' per un file servito. La ricetta in
 * CLAUDE.md per la riproduzione locale scriveva una pagina in `public/`, che e'
 * una directory versionata e andava cancellata a mano ogni volta; qui il
 * segreto vive solo nell'ambiente del job. */
const COOKIE = process.env.E2E_SESSION_COOKIE ?? "";

export const test = base.extend<{ page: Page }>({
  page: async ({ page, baseURL }, use) => {
    if (COOKIE) {
      const [name, ...resto] = COOKIE.split("=");
      const url = new URL(baseURL ?? "http://127.0.0.1:8000");
      await page.context().addCookies([{
        name, value: resto.join("="), domain: url.hostname,
        path: "/", sameSite: "Lax",
      }]);
    }
    await use(page);
  },
});

export const expect = test.expect;

/** Le rotte sorvegliate, col PAVIMENTO di contenuto che ciascuna deve
 *  raggiungere.
 *
 *  ⚠️ Il pavimento non e' un dettaglio: una pagina vuota non puo' traboccare,
 *  quindi senza di esso il gate sarebbe verde per costruzione se il seme
 *  smettesse di funzionare — la forma «un test puo' essere vero di niente» che
 *  CLAUDE.md registra quattro volte. I valori vengono da una misura reale,
 *  arrotondati per difetto perche' i dati vivi variano. */
export const ROTTE: { path: string; nome: string; minChars: number }[] = [
  { path: "/",                 nome: "Dashboard",     minChars: 600 },
  { path: "/alerts",           nome: "Segnali",       minChars: 800 },
  { path: "/setups",           nome: "In formazione", minChars: 300 },
  { path: "/positions",        nome: "Posizioni",     minChars: 200 },
  { path: "/stocks",           nome: "Screener",      minChars: 600 },
  { path: "/calendar",         nome: "Calendario",    minChars: 200 },
  { path: "/sectors",          nome: "Esplora",       minChars: 300 },
  { path: "/institutionals",   nome: "Superinvestor", minChars: 150 },
  { path: "/diagnostics",      nome: "Diagnostica",   minChars: 400 },
  { path: "/stocks/AAPL",      nome: "Dettaglio titolo", minChars: 400 },
];
