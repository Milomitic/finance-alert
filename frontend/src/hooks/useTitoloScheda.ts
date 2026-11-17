import { useEffect } from "react";

/** Il titolo della scheda del browser per le pagine di dettaglio (C-65).
 *
 *  Il guscio lo ricava dal menu, e i dettagli (/stocks/AAPL, /markets/^GSPC,
 *  /sectors/…) non sono voci di menu: le loro schede si chiamavano tutte
 *  «Finance-Alert». Senza testo non tocca niente. */
export function useTitoloScheda(testo: string | null | undefined): void {
  useEffect(() => {
    if (testo) document.title = `${testo} · Finance-Alert`;
  }, [testo]);
}
