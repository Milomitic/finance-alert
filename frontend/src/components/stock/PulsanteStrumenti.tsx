import { ChevronDown, SlidersHorizontal } from "lucide-react";

import { cn } from "@/lib/utils";

/** Il pulsante che su telefono apre indicatori, confronti e disegno del
 *  grafico (richiesta del 2026-11-22: chiusi di default, cosi' al primo
 *  caricamento il grafico arriva subito). Sta a destra della riga dei
 *  timeframe, `ml-auto`, cosi' i due controlli restano su una riga sola e
 *  allineati ai bordi della scheda. Da `sm` non esiste. */
export function PulsanteStrumenti({ aperto, onCambia }: { aperto: boolean; onCambia: () => void }) {
  return (
    <button
      type="button"
      onClick={onCambia}
      aria-expanded={aperto}
      className="ml-auto inline-flex h-7 shrink-0 items-center gap-1 rounded-md border bg-muted/30 px-2 text-xs font-semibold transition-colors hover:bg-accent sm:hidden"
    >
      <SlidersHorizontal className="h-3.5 w-3.5" aria-hidden />
      Strumenti
      <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", aperto && "rotate-180")} aria-hidden />
    </button>
  );
}
