import { Activity, Layers2, Star } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";

import { StockLogo } from "@/components/dashboard/StockLogo";
import { Card, CardContent } from "@/components/ui/card";
import { CardSkeleton } from "@/components/ui/card-skeleton";
import { SectionTitle } from "@/components/ui/section-title";
import type { LeaderRow } from "@/hooks/useSectorDetail";
import { scoreColor } from "@/lib/scoreMeta";
import { cn } from "@/lib/utils";

/* ─── LeaderboardStrip — three attention rankings, above the fold ───────── *
 *
 * Three questions about the same universe, each answered from data the engine
 * already computed. Deliberately three and not one: a single "best stocks"
 * list would have to pick a definition of best and hide the choice, and the
 * three definitions genuinely disagree — the analyst board and the technical
 * board rarely name the same stock.
 *
 * WHY EACH HEADLINE IS A 0-100 SCORE.
 * The analyst board is NOT ordered by upside to target (see the service
 * docstring: raw upside returns microcap biotech and crypto miners, because a
 * wide target gap mostly measures uncertainty). But if the headline number
 * were the upside while the order came from somewhere else, the column would
 * read +46, +54, +51, +97 top to bottom and look broken. So the headline IS
 * the ordering number, expressed on the 0-100 scale this app already speaks
 * for Qualità and Tecnico, and the upside moves into the detail line where it
 * belongs. Same colour ramp as every other composite, via `scoreColor`.
 */

interface BoardProps {
  icon: LucideIcon;
  label: string;
  /** What the board's number means, in the card header. */
  legend: string;
  rows: LeaderRow[];
  /** Integer boards (net signal count) skip the 0-100 colour ramp. */
  plainValue?: boolean;
  emptyNote: string;
}

function Board({ icon, label, legend, rows, plainValue, emptyNote }: BoardProps) {
  return (
    <Card className="h-full overflow-hidden">
      <CardContent className="p-0 h-full flex flex-col min-h-0">
        <div className="px-3 py-2 border-b bg-muted/30 shrink-0 flex items-baseline justify-between gap-2">
          <SectionTitle icon={icon} label={label} />
          <span className="text-[0.7059rem] text-muted-foreground truncate">{legend}</span>
        </div>

        {rows.length === 0 ? (
          <p className="p-3 text-xs text-muted-foreground">{emptyNote}</p>
        ) : (
          <ol className="divide-y">
            {rows.map((r, i) => (
              <li key={r.ticker}>
                <Link
                  to={`/stocks/${encodeURIComponent(r.ticker)}`}
                  className="flex items-center gap-2.5 px-3 py-1.5 hover:bg-accent/40 transition-colors"
                >
                  <span className="w-3.5 shrink-0 text-[0.7059rem] tabular-nums text-muted-foreground">
                    {i + 1}
                  </span>
                  <StockLogo ticker={r.ticker} size="xs" />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-baseline gap-1.5">
                      <span className="text-sm font-medium truncate">{r.ticker}</span>
                      <span className="text-[0.7059rem] text-muted-foreground truncate">
                        {r.name}
                      </span>
                    </span>
                    {r.detail && (
                      <span className="block text-[0.7059rem] text-muted-foreground truncate">
                        {r.detail}
                      </span>
                    )}
                  </span>
                  <span
                    className={cn(
                      "shrink-0 text-sm font-semibold tabular-nums",
                      plainValue ? "text-foreground" : scoreColor(r.value),
                    )}
                  >
                    {plainValue ? `+${r.value.toFixed(0)}` : r.value.toFixed(0)}
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}

interface Props {
  analysts: LeaderRow[];
  combined: LeaderRow[];
  signals: LeaderRow[];
  signalWindowDays: number;
  isLoading?: boolean;
}

export function LeaderboardStrip({
  analysts,
  combined,
  signals,
  signalWindowDays,
  isLoading,
}: Props) {
  if (isLoading) {
    return (
      <div className="grid gap-3 lg:grid-cols-3 [&>*]:min-w-0">
        {Array.from({ length: 3 }).map((_, i) => (
          <CardSkeleton key={i} rows={6} />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="grid gap-3 lg:grid-cols-3 [&>*]:min-w-0">
        <Board
          icon={Star}
          label="Analisti"
          legend="consenso + spazio al target"
          rows={analysts}
          emptyNote="Nessun titolo con copertura sufficiente e consenso positivo al momento."
        />
        <Board
          icon={Layers2}
          label="Qualità × Tecnico"
          legend="forte su entrambe le lenti"
          rows={combined}
          emptyNote="Nessun titolo ha entrambi i punteggi calcolati."
        />
        <Board
          icon={Activity}
          label="Segnali"
          legend={`saldo rialzista · ${signalWindowDays}g`}
          rows={signals}
          plainValue
          emptyNote={`Nessun titolo con saldo segnali positivo negli ultimi ${signalWindowDays} giorni.`}
        />
      </div>
      {/* The honesty line. Six studies on this engine came back null — the
          confirmation-count study on 14.5k signals, the factor-adjustment fit
          on 247k, the score-IC backtest on 20k observations, the regime study,
          multi-horizon, and the conditional screen on 729k. Presenting these
          boards as picks-that-will-go-up would be the one claim the evidence
          does not support, so the page says what they are instead. */}
      <p className="text-[0.7059rem] text-muted-foreground">
        Tre modi diversi di ordinare lo stesso universo, per decidere{" "}
        <strong className="font-medium">dove guardare</strong>. Non sono previsioni di
        rendimento: gli studi condotti sul motore non mostrano capacità predittiva sui
        ritorni futuri.
      </p>
    </div>
  );
}
