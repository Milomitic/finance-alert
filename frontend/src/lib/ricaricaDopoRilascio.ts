/* Dopo un rilascio, una scheda aperta col bundle VECCHIO ricarica da sola.
 *
 * Le pagine sono tutte `lazy()`, e ogni rilascio cambia i nomi dei chunk. Una
 * scheda aperta prima — la PWA sul telefono, ripresa dal background, e' il
 * caso tipico — continua a chiedere i nomi vecchi, il server risponde 404 e la
 * pagina mostra «Errore di rendering: Failed to fetch dynamically imported
 * module». Navigare altrove non aiuta: anche le altre pagine chiedono chunk del
 * bundle vecchio. Misurato in produzione il 2026-09-28 alle 16:02: 46 chunk in
 * 404, e una ricarica a mano 2,5 secondi dopo.
 *
 * ⚠️ `sw.js` e' network-first e dice di evitare «the stale-hashed-bundle
 * trap»: vale per le NAVIGAZIONI, non per il JavaScript gia' in memoria.
 *
 * Vite emette `vite:preloadError` quando fallisce un import dinamico (anche
 * l'import vero, non solo il precaricamento: `e().catch(i)` nel suo helper).
 *
 * ⚠️ La guardia e' la parte che conta. Se il chunk manca DAVVERO — un server
 * rotto, non un rilascio — una ricarica incondizionata girerebbe per sempre.
 * Se ne concede UNA per finestra; la seconda lascia l'errore all'ErrorBoundary,
 * cioe' al comportamento di prima. Senza uno storage usabile non si ricarica
 * affatto, per la stessa ragione: non si saprebbe di averlo gia' fatto. */

export const CHIAVE = "ricarica-dopo-rilascio";

/** Largo di proposito: una pagina che impiega piu' della finestra a caricarsi
 *  e a fallire ricaricherebbe in ciclo, una volta per giro. */
export const FINESTRA_MS = 60_000;

export interface Ambiente {
  storage: Pick<Storage, "getItem" | "setItem"> | null;
  ricarica: () => void;
  ora: () => number;
}

/** Ricarica se non l'ha gia' fatto nella finestra. Rende true se ha ricaricato. */
export function ricaricaSeServe({ storage, ricarica, ora }: Ambiente): boolean {
  if (!storage) return false;
  try {
    const adesso = ora();
    const prima = Number(storage.getItem(CHIAVE));
    if (prima > 0 && adesso - prima < FINESTRA_MS) return false;
    storage.setItem(CHIAVE, String(adesso));
  } catch {
    return false;
  }
  ricarica();
  return true;
}

function sessione(win: Window): Storage | null {
  try {
    // Leggere `sessionStorage` puo' gia' lanciare, con i dati del sito bloccati.
    return win.sessionStorage;
  } catch {
    return null;
  }
}

export function installaRicaricaDopoRilascio(win: Window = window): void {
  win.addEventListener("vite:preloadError", () => {
    ricaricaSeServe({ storage: sessione(win), ricarica: () => win.location.reload(), ora: Date.now });
  });
}
