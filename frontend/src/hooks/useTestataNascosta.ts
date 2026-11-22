import { type RefObject, useEffect, useState } from "react";

/** Vero quando la testata va nascosta: chi scorre in GIU' il contenitore
 *  oltre la sua altezza, falso appena torna in SU o vicino alla cima
 *  (richiesta del 2026-11-22: su telefono la testata ruba spazio ai dati).
 *
 *  `soglia` ignora i tremolii del dito: sotto quei pixel di movimento non
 *  cambia niente. `chiave` (il percorso) la rimostra a ogni cambio pagina. */
export function useTestataNascosta(
  ref: RefObject<HTMLElement | null>,
  { altezza = 56, soglia = 8, chiave }: { altezza?: number; soglia?: number; chiave?: unknown } = {},
): boolean {
  const [nascosta, setNascosta] = useState(false);
  const [chiavePrec, setChiavePrec] = useState(chiave);
  if (chiave !== chiavePrec) {
    setChiavePrec(chiave);
    setNascosta(false);
  }

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let ultimo = el.scrollTop;
    const onScroll = () => {
      const y = el.scrollTop;
      if (y <= altezza) {
        setNascosta(false);
      } else if (y - ultimo > soglia) {
        setNascosta(true);
      } else if (ultimo - y > soglia) {
        setNascosta(false);
      } else {
        return;
      }
      ultimo = y;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [ref, altezza, soglia]);

  return nascosta;
}
