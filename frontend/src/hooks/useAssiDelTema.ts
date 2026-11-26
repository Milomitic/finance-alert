import { type RefObject, useEffect, useState } from "react";

import { opzioniAssi, temaScuroOra } from "@/lib/coloriGrafico";

/** Vero col tema scuro, e segue il cambio di tema senza ricaricare: osserva
 *  la classe `dark` di `<html>`, l'unico posto dove `useTheme` la scrive. */
export function useTemaScuro(): boolean {
  const [scuro, setScuro] = useState(temaScuroOra);
  useEffect(() => {
    const html = document.documentElement;
    const osservatore = new MutationObserver(() => setScuro(html.classList.contains("dark")));
    osservatore.observe(html, { attributes: true, attributeFilter: ["class"] });
    return () => osservatore.disconnect();
  }, []);
  return scuro;
}

/** Riapplica assi e griglia del tema a un grafico gia' creato. La creazione
 *  legge `temaScuroOra()` da se': questo effetto serve per il cambio di tema
 *  a pagina aperta, quando il grafico non si ricrea. */
export function useAssiDelTema(grafico: RefObject<{ applyOptions: (o: object) => void } | null>): void {
  const scuro = useTemaScuro();
  useEffect(() => {
    grafico.current?.applyOptions(opzioniAssi(scuro));
  }, [grafico, scuro]);
}
