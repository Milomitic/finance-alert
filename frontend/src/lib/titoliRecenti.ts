/** I titoli aperti di recente (FA-112): proprietario unico.
 *
 *  ⚠️ Prima vivevano dentro la ricerca della barra, e si registravano solo
 *  quando un titolo si apriva DALLA RICERCA. I percorsi piu' usati — le liste
 *  del cruscotto, i segnali, lo screener — non lasciavano traccia, quindi
 *  «visti di recente» elencava soprattutto i titoli cercati, non quelli visti.
 *  Ora li registra la pagina titolo stessa, da qualunque parte si arrivi.
 *
 *  La chiave resta quella di prima, cosi' la lista di chi aveva gia' usato la
 *  ricerca non si perde. Ogni accesso sta in try/catch: una finestra privata o
 *  un blocco dei dati del sito possono far sollevare `localStorage`. */
const CHIAVE = "stock-search-recent";
export const RECENTI_MAX = 8;

export function leggiRecenti(): string[] {
  try {
    const raw = localStorage.getItem(CHIAVE);
    const lista: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(lista) ? lista.filter((t): t is string => typeof t === "string") : [];
  } catch {
    return [];
  }
}

export function aggiungiRecente(ticker: string): void {
  if (!ticker) return;
  try {
    const lista = [ticker, ...leggiRecenti().filter((t) => t !== ticker)];
    localStorage.setItem(CHIAVE, JSON.stringify(lista.slice(0, RECENTI_MAX)));
  } catch {
    // quota piena o archiviazione bloccata: i recenti sono una comodita'
  }
}
