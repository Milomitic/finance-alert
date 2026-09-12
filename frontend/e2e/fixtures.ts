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
    const base = baseURL ?? "http://127.0.0.1:8000";
    if (COOKIE) {
      const [name, ...resto] = COOKIE.split("=");
      const url = new URL(base);
      await page.context().addCookies([{
        name, value: resto.join("="), domain: url.hostname,
        path: "/", sameSite: "Lax",
      }]);
    }

    /* ⚠️ La sessione si verifica PRIMA, non si spera.
     *
     * Al primo passaggio in CI ogni rotta rendeva 0 caratteri e il gate
     * riportava «la pagina e' vuota»: vero, ma la causa stava a monte — senza
     * una sessione valida `ProtectedRoute` rimanda al login, che non ha un
     * <main>. Un messaggio che descrive il sintomo invece della causa fa
     * cercare nel posto sbagliato, e qui il posto sbagliato e' il layout.
     *
     * Una chiamata a un endpoint PROTETTO risponde alla domanda giusta in un
     * colpo solo: se non e' 200 il problema e' il cookie, non il CSS. */
    const risposta = await page.request.get(`${base}/api/platform/health`);
    if (risposta.status() !== 200) {
      throw new Error(
        `Sessione non valida: GET /api/platform/health ha risposto ` +
        `${risposta.status()}. ${COOKIE ? "Il cookie e' stato impostato ma non e' accettato" : "E2E_SESSION_COOKIE non e' impostato"} — ` +
        `il gate misurerebbe la pagina di login, non l'app. ` +
        `Corpo: ${(await risposta.text()).slice(0, 200)}`,
      );
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
