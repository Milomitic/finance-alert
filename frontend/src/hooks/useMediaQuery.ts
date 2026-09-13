import * as React from "react";

/* Subscribe to a CSS media query from JS.
 *
 * Tailwind handles anything that is purely a matter of styling. This is for
 * the cases it structurally cannot reach: the CONTENT itself has to change,
 * not its presentation. A placeholder attribute, a label string, how many
 * items a list renders — CSS can hide those but cannot shorten them, and a
 * hidden-but-present string still gets measured, still gets read aloud, and
 * still truncates.
 *
 * Initialised from a real match rather than from `false`, so a small screen
 * never paints the desktop variant for one frame before correcting itself.
 */
export function useMediaQuery(query: string): boolean {
  /* ⚠️ `useSyncExternalStore` e non `useState` + `useEffect`.
   *
   * La forma precedente leggeva il match una volta per inizializzare lo stato
   * e poi lo RILEGGEVA dentro un effect per risincronizzarsi. Funziona, e ha
   * tre difetti che questa API toglie di netto:
   *
   *   - una renderizzazione a cascata a ogni montaggio (lo stato viene
   *     riscritto subito dopo il primo render, anche quando il valore non e'
   *     cambiato). E' cio' che `react-hooks/set-state-in-effect` segnalava;
   *   - una finestra di DISALLINEAMENTO fra il primo render e l'effect: se la
   *     larghezza cambia in quei millisecondi, il valore letto in render e'
   *     gia' vecchio e nessuno se ne accorge;
   *   - due copie della stessa lettura da tenere d'accordo a mano.
   *
   * `useSyncExternalStore` e' scritto per esattamente questo: React chiama
   * `leggi` quando serve e si ri-sottoscrive da solo quando `query` cambia.
   *
   * ⚠️ Il terzo argomento e' lo snapshot LATO SERVER. Non c'e' SSR qui, ma
   * senza di esso l'hook lancia in qualunque ambiente privo di `window` — per
   * esempio dentro un test che monta un componente prima che jsdom sia
   * pronto. `false` significa «nessun match», che e' il ramo conservativo:
   * la stessa scelta che la versione precedente faceva nel suo guard.
   */
  const sottoscrivi = React.useCallback(
    (cambiato: () => void) => {
      if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
        return () => {};
      }
      const mql = window.matchMedia(query);
      mql.addEventListener("change", cambiato);
      return () => mql.removeEventListener("change", cambiato);
    },
    [query],
  );

  const leggi = React.useCallback(
    () =>
      typeof window !== "undefined" && typeof window.matchMedia === "function"
        ? window.matchMedia(query).matches
        : false,
    [query],
  );

  return React.useSyncExternalStore(sottoscrivi, leggi, () => false);
}

/** Below Tailwind's `sm` (640px) — i.e. phones. Kept as one constant so the
 *  JS breakpoint can never drift away from the CSS one. */
export const useIsPhone = () => useMediaQuery("(max-width: 639px)");

/** Below Tailwind's `md` (768px). Stessa ragione del costante qui sopra: la
 *  soglia JS non deve poter divergere da quella CSS. La usa
 *  `StockBrowserTable`, che ha due layout completi — righe di tabella e card
 *  — e ne deve montare UNO SOLO. */
export const useIsBelowMd = () => useMediaQuery("(max-width: 767px)");
