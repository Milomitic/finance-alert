import { ChevronRight } from "lucide-react";
import { useMemo } from "react";

import type { CalendarEvent } from "@/api/types";
import { formatLongDate, todayISO } from "@/lib/calendarMeta";
import { cn } from "@/lib/utils";

import { EventChip } from "./EventChip";

/** Il calendario come elenco, sotto `lg` (D-61, A-46, A-55).
 *
 *  A 375px la griglia del mese ha celle da ~50px: un chip leggibile ne vuole
 *  ~81, quindi restavano tre pallini senza nome (misurato in produzione), e
 *  a 768px 115 testi troncati. Qui solo i giorni che hanno eventi, uno sotto
 *  l'altro, a tutta larghezza: l'identita' — il ticker, la serie macro — non
 *  e' piu' cio' che cede.
 *
 *  Il tocco sull'intestazione del giorno apre il dettaglio; i chip restano
 *  quelli della griglia (una trimestrale porta al titolo). */
export function AgendaCalendario({
  events,
  daISO,
  aISO,
  selectedDate,
  onSelectDate,
  isLoading = false,
}: {
  events: CalendarEvent[];
  /** Gli estremi del periodo visibile: il mese o la settimana, senza i
   *  giorni di bordo che la griglia del mese mostra per completare le righe. */
  daISO: string;
  aISO: string;
  selectedDate: string | null;
  onSelectDate: (iso: string) => void;
  isLoading?: boolean;
}) {
  const oggi = todayISO();
  const giorni = useMemo(() => {
    const perGiorno = new Map<string, CalendarEvent[]>();
    for (const e of events) {
      if (e.date < daISO || e.date > aISO) continue;
      const lista = perGiorno.get(e.date);
      if (lista) lista.push(e);
      else perGiorno.set(e.date, [e]);
    }
    return [...perGiorno.entries()].sort(([a], [b]) => (a < b ? -1 : 1));
  }, [events, daISO, aISO]);

  if (isLoading) {
    return (
      <div className="space-y-3" aria-busy="true">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-24 animate-pulse rounded-xl border bg-muted/30" />
        ))}
      </div>
    );
  }
  if (giorni.length === 0) return null;

  return (
    <ol className="space-y-3">
      {giorni.map(([iso, lista]) => (
        <li
          key={iso}
          className={cn(
            "rounded-xl border bg-card",
            iso === oggi && "border-primary/60",
            iso === selectedDate && "ring-2 ring-ring",
          )}
        >
          <button
            type="button"
            onClick={() => onSelectDate(iso)}
            className="flex min-h-11 w-full items-center gap-2 border-b px-3 text-left text-sm font-semibold"
          >
            <span className="flex-1">
              {formatLongDate(iso)}
              {iso === oggi && <span className="ml-2 text-xs font-medium text-primary">oggi</span>}
            </span>
            <span className="text-xs font-normal text-muted-foreground tabular-nums">
              {lista.length} {lista.length === 1 ? "evento" : "eventi"}
            </span>
            <ChevronRight className="h-4 w-4 text-muted-foreground" aria-hidden />
          </button>
          <div className="flex flex-wrap gap-1.5 p-2">
            {lista.map((e, i) => (
              <EventChip key={`${e.kind}-${i}`} event={e} tabIndex={0} />
            ))}
          </div>
        </li>
      ))}
    </ol>
  );
}
