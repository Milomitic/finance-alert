import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

import { registraPagina } from "@/api/uso";
import { PAGINE_A_VISTE } from "@/lib/rotteUso";

/** Conta ogni pagina aperta (FA-114).
 *
 *  ⚠️ Non e' il RUM: i Web Vitals descrivono il caricamento di un DOCUMENTO,
 *  e in una SPA la navigazione interna non ne carica uno nuovo — contandoli si
 *  conterebbero gli F5, non le pagine. Qui si conta ogni cambio di pagina.
 *
 *  La chiave e' il percorso, piu' la vista sulle pagine che la usano come
 *  navigazione. Cambiare filtri, ordinamento o timeframe non e' aprire una
 *  pagina e non si conta. Il ref tiene fuori il doppio effetto di StrictMode
 *  in sviluppo. */
export function UsoPagineReporter() {
  const { pathname, search } = useLocation();
  const vista = PAGINE_A_VISTE.has(pathname) ? new URLSearchParams(search).get("vista") : null;
  const chiave = `${pathname}|${vista ?? ""}`;
  const ultima = useRef<string | null>(null);

  useEffect(() => {
    if (ultima.current === chiave) return;
    ultima.current = chiave;
    // Un contatore che fallisce non deve disturbare chi naviga.
    registraPagina(pathname, vista).catch(() => undefined);
  }, [chiave, pathname, vista]);

  return null;
}
