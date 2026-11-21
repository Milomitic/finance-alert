import { ApiError } from "@/api/client";

/** Che cosa e' andato storto, in italiano e per chi usa l'app (B-76).
 *
 *  Gli errori mostravano il `detail` di FastAPI («User not found», un 422 col
 *  percorso del campo) o «Failed to fetch», e quasi ovunque la stessa frase
 *  «Errore nel caricamento» senza dire QUALE guasto: sessione scaduta, troppe
 *  richieste (il limitatore dell'ingress e' a 50 al secondo), server o rete.
 *  Il messaggio e' l'unica diagnosi che chi usa l'app ha. Null quando non
 *  c'e' niente di piu' utile da dire. */
export function messaggioErrore(e: unknown): string | null {
  if (e instanceof ApiError) {
    if (e.status === 401) return "La sessione è scaduta: accedi di nuovo.";
    if (e.status === 403) return "Accesso non consentito.";
    if (e.status === 404) return "Il dato richiesto non esiste.";
    if (e.status === 429) return "Troppe richieste in poco tempo: riprova fra qualche secondo.";
    if (e.status === 503) return "La fonte dei dati non risponde in questo momento.";
    if (e.status >= 500) return "Il server ha avuto un problema.";
    if (e.status >= 400) return "La richiesta non è valida.";
    return null;
  }
  if (e instanceof TypeError || (e instanceof Error && /fetch|network/i.test(e.message))) {
    return "Connessione assente o interrotta.";
  }
  return null;
}
