import { ArrowUpDown } from "lucide-react";
import { useState } from "react";

import type { AlertConflitto } from "@/api/types";
import { AlertDetailDialog } from "@/components/AlertDetailDialog";
import { useAlert } from "@/hooks/useAlerts";
import { getAlertKindMeta } from "@/lib/alertMeta";

/* ─── Segnali in conflitto (FA-151) ──────────────────────────────────────
 *
 * Lo stesso titolo ha un alert del verso opposto nato entro un giorno. I due
 * restano, perche' il magazzino degli esiti li misura separati: questo dice
 * soltanto a chi legge che il motore, quel giorno, sul titolo non ha detto
 * niente di netto.
 *
 * ⚠️ Colori NEUTRI di proposito: rose/emerald dicono la direzione, e una
 * pastiglia che contraddice una direzione non ne ha una sua. */

function verso(tone: string): string {
  return tone === "bull" ? "rialzista" : tone === "bear" ? "ribassista" : tone;
}

/** La pastiglia sulla riga della lista. */
export function PastigliaConflitto({ c }: { c: AlertConflitto | null | undefined }) {
  if (!c) return null;
  return (
    <span className="inline-flex shrink-0 items-center gap-0.5 self-center rounded border border-border px-1 text-[0.6875rem] leading-4 text-muted-foreground">
      <ArrowUpDown className="h-2.5 w-2.5" aria-hidden />
      in conflitto
    </span>
  );
}

/** La riga nel dialogo, col collegamento all'altro alert. */
export function RigaConflitto({ c }: { c: AlertConflitto | null | undefined }) {
  const [apri, setApri] = useState<number | null>(null);
  const altro = useAlert(apri);
  if (!c) return null;
  const nome = c.signal_name ? getAlertKindMeta(`signal:${c.signal_name}`).label : "un altro segnale";
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-md border border-border bg-muted/40 px-3 py-2 text-xs">
      <ArrowUpDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
      <span className="min-w-0">
        <span className="font-semibold">In conflitto:</span> {"sullo stesso titolo c'è un segnale "}
        {verso(c.tone)} ({nome}) nato entro un giorno. Quel giorno il motore non ha detto niente di netto.
      </span>
      <button
        type="button"
        className="font-semibold underline-offset-2 hover:underline"
        onClick={() => setApri(c.alert_id)}
      >
        {"Apri l'altro"}
      </button>
      {apri != null && (
        <AlertDetailDialog alert={altro.data ?? null} onClose={() => setApri(null)} />
      )}
    </div>
  );
}
