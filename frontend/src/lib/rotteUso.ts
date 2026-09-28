/** Le pagine che hanno le viste nel parametro `vista` (FA-114).
 *
 *  ⚠️ Gemello di `VISTE` in `backend/app/core/rotte.py`. Il reporter manda la
 *  vista SOLO per queste: altrove un parametro `vista` estraneo conterebbe come
 *  una pagina nuova a ogni cambio. */
export const PAGINE_A_VISTE: ReadonlySet<string> = new Set(["/alerts", "/diagnostics"]);

/** Il nome leggibile di una chiave del contatore. Le chiavi sono quelle che il
 *  server scrive: forma della pagina, e per le pagine a viste la vista. */
const NOMI: Record<string, string> = {
  "/": "Dashboard",
  "/alerts?vista=segnali": "Segnali",
  "/alerts?vista=formazione": "Segnali · In formazione",
  "/alerts?vista=esiti": "Segnali · Esiti",
  "/positions": "Posizioni",
  "/stocks": "Screener",
  "/stocks/:ticker": "Dettaglio titolo",
  "/sectors": "Esplora",
  "/sectors/:name": "Dettaglio settore",
  "/calendar": "Calendario",
  "/institutionals": "Superinvestor",
  "/institutionals/:slug": "Dettaglio fondo",
  "/markets/:symbol": "Dettaglio mercato",
  "/macro/:seriesId": "Serie macro",
  "/diagnostics?vista=piattaforma": "Diagnostica · Piattaforma",
  "/diagnostics?vista=motore": "Diagnostica · Motore",
  "/other": "Altre pagine (indirizzo sconosciuto)",
};

export function nomePagina(chiave: string): string {
  return NOMI[chiave] ?? chiave;
}
