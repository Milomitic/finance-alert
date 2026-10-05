import { useMemo } from "react";

import { useEtoroPortafoglio } from "@/hooks/useEtoro";
import { usePositions } from "@/hooks/usePositions";
import { usePreferiti } from "@/hooks/usePreferiti";
import type { Rilevanza } from "@/lib/settimana";

/** I titoli che contano — posizioni aperte e preferiti — come mappa
 *  ticker -> rilevanza, lo specchio lato client di `rilevanza_service`.
 *
 *  Proprietario unico dal 2026-09-29: prima la scheda «Questa settimana» se la
 *  costruiva da sola, e con il calendario e i movers del cruscotto i
 *  consumatori sarebbero diventati tre copie della stessa regola.
 *
 *  `pronto` e' falso finche' la lista dei preferiti non e' arrivata: un
 *  filtro «solo i miei titoli» applicato prima renderebbe una lista vuota che
 *  si legge come «nessun evento», cioe' una risposta falsa. */
export function useTitoliSeguiti(): { titoli: ReadonlyMap<string, Rilevanza>; pronto: boolean } {
  const preferitiQ = usePreferiti();
  const posizioniQ = usePositions();
  const etoroQ = useEtoroPortafoglio();
  const titoli = useMemo(() => {
    const m = new Map<string, Rilevanza>();
    for (const p of preferitiQ.data ?? []) m.set(p.ticker, "preferito");
    // Una posizione vince su un preferito dello stesso titolo, come nel server.
    for (const p of posizioniQ.data ?? []) if (!p.closed_at) m.set(p.ticker, "posizione");
    // E quelle aperte su eToro (FA-124), solo se abbinate al catalogo.
    for (const p of etoroQ.data?.aperte ?? []) if (p.ticker) m.set(p.ticker, "posizione");
    return m;
  }, [preferitiQ.data, posizioniQ.data, etoroQ.data]);
  const pronto = preferitiQ.data !== undefined || preferitiQ.isError;
  return { titoli, pronto };
}
