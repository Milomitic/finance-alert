/** Dove portare l'utente dopo l'accesso (D-89).
 *
 * `ProtectedRoute` passa la posizione da cui la sessione l'ha mandato al
 * login; qui la si accetta solo se e' un percorso INTERNO. Un valore che
 * arriva dallo stato della cronologia non e' fidato: `//esempio.com` e'
 * un indirizzo assoluto per il browser, e tornare su `/login` farebbe un
 * giro a vuoto. Tutto cio' che non torna e' la dashboard, come prima. */

type Posizione = { pathname?: unknown; search?: unknown; hash?: unknown };

export function destinazioneDopoLogin(stato: unknown): string {
  const da = (stato as { da?: Posizione } | null | undefined)?.da;
  const percorso = typeof da?.pathname === "string" ? da.pathname : "";
  if (!percorso.startsWith("/") || percorso.startsWith("//") || percorso.startsWith("/login")) {
    return "/";
  }
  const s = typeof da?.search === "string" && da.search.startsWith("?") ? da.search : "";
  const h = typeof da?.hash === "string" && da.hash.startsWith("#") ? da.hash : "";
  return percorso + s + h;
}
