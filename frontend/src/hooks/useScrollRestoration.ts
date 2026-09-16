import { useEffect, useLayoutEffect, useRef, type RefObject } from "react";
import { useLocation, useNavigationType } from "react-router-dom";

/* ─── Lo scorrimento di <main> segue la cronologia ─────────────────────────
 *
 * Trovato nel collaudo in browser del 2026-09-16. Lo scorrimento dell'app non
 * e' quello della finestra — `html` e `body` sono `overflow-x: clip` e il
 * contenuto scorre dentro `<main>` — e `<main>` e' LO STESSO elemento per ogni
 * pagina. Nessuno ne gestiva la posizione, quindi:
 *
 * - aprendo un titolo da una lista scorsa a 2.500px, la pagina del titolo
 *   partiva a 2.500px, a meta';
 * - tornando indietro, la lista si ritrovava dove la pagina del titolo l'aveva
 *   lasciata (in fondo), non dove la si era lasciata.
 *
 * `ScrollRestoration` di react-router gestisce solo la finestra, e solo con un
 * data router; questa app usa `BrowserRouter`. Tre regole, per tipo di
 * navigazione:
 *
 * - PUSH: una pagina nuova parte dall'alto;
 * - POP (indietro/avanti): torna la posizione salvata per quella voce;
 * - REPLACE: non si tocca. I filtri scrivono l'URL con `replace`, e cambiare
 *   filtro non deve far saltare la vista.
 */

/** Quanto aspettare che il contenuto sia alto abbastanza da contenere la
 *  posizione salvata: i dati arrivano dopo il primo render. */
const TENTATIVI = 30;
const INTERVALLO_MS = 50;

export function useScrollRestoration(ref: RefObject<HTMLElement | null>) {
  const location = useLocation();
  const tipo = useNavigationType();
  const posizioni = useRef(new Map<string, number>());
  const chiaveCorrente = useRef(location.key);

  // La posizione si registra mentre si scorre, non al cambio di pagina: quando
  // l'effetto del cambio gira il DOM e' gia' quello nuovo, e `scrollTop` puo'
  // essere gia' stato ridotto dal contenuto piu' corto.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const registra = () => {
      posizioni.current.set(chiaveCorrente.current, el.scrollTop);
    };
    el.addEventListener("scroll", registra, { passive: true });
    return () => el.removeEventListener("scroll", registra);
  }, [ref]);

  useLayoutEffect(() => {
    const el = ref.current;
    chiaveCorrente.current = location.key;
    if (!el || tipo === "REPLACE") return;
    if (tipo === "PUSH") {
      el.scrollTop = 0;
      return;
    }
    const obiettivo = posizioni.current.get(location.key) ?? 0;
    let tentativi = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const prova = () => {
      tentativi += 1;
      if (el.scrollHeight - el.clientHeight >= obiettivo || tentativi >= TENTATIVI) {
        el.scrollTop = obiettivo;
        return;
      }
      timer = setTimeout(prova, INTERVALLO_MS);
    };
    prova();
    return () => clearTimeout(timer);
  }, [ref, location.key, tipo]);
}
