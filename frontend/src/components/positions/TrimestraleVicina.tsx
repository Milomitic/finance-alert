import { CalendarClock } from "lucide-react";

import { earningsProximityDays } from "@/lib/earningsProximity";

/** Finestra in cui la prossima trimestrale di una posizione aperta si mostra. */
export const FINESTRA_TRIMESTRALE_GG = 14;

/** La prossima trimestrale di una posizione aperta, se cade entro due
 *  settimane.
 *
 *  Sta sotto la geometria, non accanto al ticker. La colonna avverte gia' che
 *  «la distanza dallo stop non e' la perdita massima, perche' un gap apre dove
 *  trova mercato», e la trimestrale e' l'evento che quel gap lo produce. E un
 *  elemento accanto al ticker toglierebbe larghezza al nome, l'unica traccia
 *  flessibile della riga (vedi `EarningsMarker` in `SetupConditionGroup`).
 *
 *  Ambra come ogni marcatore di trimestrale dell'app: una trimestrale non ha
 *  direzione, e rosa/smeraldo significano direzione. La sera prima arriva
 *  anche il promemoria Telegram (`promemoria_trimestrali_service`). */
export function TrimestraleVicina({ data }: { data: string | null | undefined }) {
  const gg = earningsProximityDays(data, FINESTRA_TRIMESTRALE_GG);
  if (gg === null) return null;
  const quando = gg === 0 ? "oggi" : gg === 1 ? "domani" : `fra ${gg} giorni`;
  return (
    <div
      className="mt-1 inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-semibold bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300"
      title={`Trimestrale il ${data?.slice(0, 10)}: un gap puo' aprire oltre lo stop`}
    >
      <CalendarClock className="h-3 w-3" aria-hidden="true" />
      Trimestrale {quando}
    </div>
  );
}
