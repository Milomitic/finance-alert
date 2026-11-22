import { Check, X } from "lucide-react";
import type { ReactNode } from "react";

import type { Alert } from "@/api/types";
import { AlertKindChip, AlertNatureChip } from "@/components/AlertChips";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { TableSearchInput } from "@/components/ui/table-search-input";
import { formatShortDate, giornoDelSegnale } from "@/lib/alertDates";
import { snapshotForza } from "@/lib/alertMeta";
import { TESTO_GIU, TESTO_SU } from "@/lib/toni";
import { cn } from "@/lib/utils";

/* ─── I segnali su telefono: un elenco, non una tabella (2026-11-22) ──────
 *
 * Su 412px la tabella dei segnali chiedeva lo scorrimento laterale per
 * leggere Forza ed esito. Qui ogni segnale e' un bottone su due righe, come
 * gli Esiti: chi (titolo, Forza), poi che cosa e quando (tipo, direzione,
 * giorno, esito). Il resto sta nel dettaglio, che si apre al tocco.
 *
 * ⚠️ Il ramo telefono/tabella si sceglie in JS (`useIsPhone`) in chi lo usa,
 * non con `hidden`: due copie montate sarebbero due alberi letti dagli
 * assistivi e misurati dal gate. */

function toneForza(f: number): string {
  if (f >= 70) return TESTO_SU;
  if (f >= 50) return "text-amber-700 dark:text-amber-400";
  return TESTO_GIU;
}

function Esito({ a }: { a: Alert }) {
  if (a.outcome_hit == null) return null;
  const fwd = a.outcome_fwd_return;
  const pct = fwd != null ? `${fwd >= 0 ? "+" : ""}${(fwd * 100).toFixed(1)}%` : "";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 rounded px-1 py-0.5 text-[0.7059rem] font-semibold tabular-nums",
        a.outcome_hit
          ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300"
          : "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300",
      )}
    >
      {a.outcome_hit ? <Check className="h-3 w-3" aria-hidden /> : <X className="h-3 w-3" aria-hidden />}
      <span className="sr-only">{a.outcome_hit ? "direzione azzeccata" : "direzione mancata"}</span>
      {pct}
    </span>
  );
}

interface Props {
  alerts: Alert[];
  onRowClick: (a: Alert) => void;
  q: string;
  onQueryChange: (v: string) => void;
  vuoto?: ReactNode;
}

export function ElencoSegnaliCompatto({ alerts, onRowClick, q, onQueryChange, vuoto }: Props) {
  return (
    <div>
      <div className="border-b p-2">
        <TableSearchInput
          value={q}
          onChange={onQueryChange}
          placeholder="cerca ticker o nome…"
          ariaLabel="Filtra per ticker o nome"
          className="w-full"
        />
      </div>
      {alerts.length === 0 ? (
        <div className="p-6 text-center text-sm text-muted-foreground">
          {vuoto ?? "Nessun segnale con questi filtri."}
        </div>
      ) : (
        <ul className="divide-y">
          {alerts.map((a) => {
            const forza = snapshotForza(a.snapshot as Record<string, unknown> | undefined);
            return (
              <li key={a.id}>
                <button
                  type="button"
                  onClick={() => onRowClick(a)}
                  className="flex w-full flex-col gap-1 px-3 py-2 text-left hover:bg-muted/50"
                >
                  <span className="flex w-full min-w-0 items-center gap-2">
                    <StockLogo ticker={a.ticker ?? ""} size="xs" />
                    <span className="shrink-0 font-semibold">{a.ticker ?? "—"}</span>
                    <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">{a.name}</span>
                    {forza != null && (
                      <span className={cn("shrink-0 text-sm font-semibold tabular-nums", toneForza(forza))}>
                        <span className="sr-only">Forza </span>
                        {Math.round(forza)}%
                      </span>
                    )}
                  </span>
                  <span className="flex w-full min-w-0 items-center gap-1.5">
                    <AlertKindChip alert={a} size="sm" breve />
                    <AlertNatureChip alert={a} size="sm" breve />
                    <span className="ml-auto shrink-0 text-xs tabular-nums text-muted-foreground">
                      {formatShortDate(giornoDelSegnale(a))}
                    </span>
                    <Esito a={a} />
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
