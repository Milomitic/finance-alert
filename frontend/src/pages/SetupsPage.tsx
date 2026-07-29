import { Clock, Hourglass, Target, TrendingDown, TrendingUp } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { StockIdentity } from "@/components/dashboard/StockIdentity";
import { Card, CardContent } from "@/components/ui/card";
import { CardSkeleton } from "@/components/ui/card-skeleton";
import { QueryError } from "@/components/ui/query-error";
import { SectionTitle } from "@/components/ui/section-title";
import { useSetups, waitingDays, type Setup } from "@/hooks/useSetups";
import { getAlertKindMeta } from "@/lib/alertMeta";
import { cn } from "@/lib/utils";

/* ─── Setups — cosa si sta formando, PRIMA del segnale ─────────────────────
 *
 * Design constraint that drives everything here: this page must not read like
 * the Segnali page. A setup is a wait, not a call. So:
 *
 *   - no Probabilità anywhere, because setups have none;
 *   - `convenience` is labelled "priorità" and explained as ordering, never
 *     shown as a percentage next to a price;
 *   - the biggest text on each row is "cosa manca" — the thing you act on;
 *   - the wait is stated in days, because lead time is the whole product.
 *
 * If this page ever starts looking like a list of predictions, the honesty
 * the backend was built around has leaked away at the last step.
 */

function ProximityBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2 min-w-0">
      <div className="h-1.5 w-16 shrink-0 rounded-full bg-muted overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full",
            // Literal class strings (Tailwind purger, per CLAUDE.md).
            value >= 0.8 ? "bg-emerald-500" : value >= 0.6 ? "bg-sky-500" : "bg-amber-500",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs tabular-nums text-muted-foreground shrink-0">{pct}%</span>
    </div>
  );
}

function SetupRow({ setup }: { setup: Setup }) {
  const meta = getAlertKindMeta(setup.detector);
  const days = waitingDays(setup);
  const bull = setup.tone === "bull";
  const level = setup.annotations?.levels?.[0];

  return (
    <div className="rounded-lg border bg-card p-3 hover:bg-muted/30 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <Link
          to={`/stocks/${encodeURIComponent(setup.ticker)}`}
          className="flex items-center gap-2 min-w-0 hover:underline"
        >
          <StockIdentity ticker={setup.ticker} name={setup.name} />
        </Link>
        <div className="shrink-0 text-right">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-mono">
            Priorità
          </div>
          <div className="text-lg font-semibold tabular-nums leading-none">
            {Math.round(setup.convenience)}
          </div>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <span
          className={cn(
            "inline-flex items-center gap-1 text-xs font-semibold",
            bull ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400",
          )}
        >
          {bull ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
          {meta.label}
        </span>
        <ProximityBar value={setup.proximity} />
        {days !== null && (
          <span
            className="inline-flex items-center gap-1 text-xs text-muted-foreground"
            title="Da quanto queste condizioni si mantengono"
          >
            <Clock className="h-3 w-3" aria-hidden />
            in attesa da {days === 0 ? "oggi" : `${days}g`}
          </span>
        )}
      </div>

      {/* The actionable part, deliberately the most legible thing on the row. */}
      <div className="mt-2 flex items-start gap-2 rounded-md bg-muted/50 px-2.5 py-2">
        <Target className="h-3.5 w-3.5 mt-0.5 shrink-0 text-muted-foreground" aria-hidden />
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-mono">
            Cosa manca
          </div>
          <div className="text-sm leading-snug">{setup.missing}</div>
          {level && (
            <div className="mt-1 text-xs text-muted-foreground tabular-nums">
              {level.label}: {level.price.toFixed(2)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/** The feature's own report card. Shown up front on purpose: setups make no
 *  market claim, so the only honest thing to advertise is whether they do
 *  what they say — convert, and with how much warning. */
function StatsStrip({ stats }: { stats: ReturnType<typeof useSetups>["data"] extends undefined ? never : NonNullable<ReturnType<typeof useSetups>["data"]>["stats"] }) {
  const tiles = [
    { label: "In formazione", value: String(stats.active) },
    {
      label: "Tasso conversione",
      // null means "nothing has resolved yet" — rendering it as 0% would
      // read as "setups never work", which is a different claim entirely.
      value: stats.conversion_rate === null ? "—" : `${Math.round(stats.conversion_rate * 100)}%`,
      hint: stats.conversion_rate === null ? "nessuno ancora risolto" : `${stats.converted} su ${stats.converted + stats.expired}`,
    },
    {
      label: "Anticipo medio",
      value: stats.avg_lead_days === null ? "—" : `${stats.avg_lead_days}g`,
      hint: "giorni di preavviso reali",
    },
  ];
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 [&>*]:min-w-0">
      {tiles.map((t) => (
        <Card key={t.label}>
          <CardContent className="p-3">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-mono">
              {t.label}
            </div>
            <div className="text-2xl font-bold tabular-nums leading-tight mt-0.5">{t.value}</div>
            {t.hint && <div className="text-xs text-muted-foreground mt-0.5">{t.hint}</div>}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export default function SetupsPage() {
  const [tone, setTone] = useState<"bull" | "bear" | undefined>(undefined);
  const q = useSetups(tone);

  return (
    <div className="space-y-4 max-w-5xl">
      <div>
        <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight flex items-center gap-3">
          <Hourglass className="h-7 w-7 text-muted-foreground" aria-hidden />
          In formazione
        </h2>
        <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
          Condizioni che stanno convergendo, <strong>prima</strong> che il segnale scatti —
          così hai il tempo di preparare una posizione. Non sono previsioni: descrivono
          lo stato di oggi e dicono cosa manca perché il segnale si attivi.
        </p>
      </div>

      {q.data && <StatsStrip stats={q.data.stats} />}

      <div className="flex items-center gap-2">
        {([undefined, "bull", "bear"] as const).map((t) => (
          <button
            key={t ?? "all"}
            type="button"
            onClick={() => setTone(t)}
            className={cn(
              "min-h-[36px] px-3 rounded-md border text-xs font-semibold transition-colors",
              tone === t ? "bg-primary text-primary-foreground" : "hover:bg-accent",
            )}
          >
            {t === undefined ? "Tutti" : t === "bull" ? "Rialzisti" : "Ribassisti"}
          </button>
        ))}
      </div>

      <div>
        <SectionTitle icon={Target} label="Setup attivi" className="mb-3" />
        {q.isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <CardSkeleton key={i} rows={2} className="h-[110px]" />
            ))}
          </div>
        ) : q.isError ? (
          <QueryError message="dei setup" onRetry={q.refetch} isRetrying={q.isFetching} />
        ) : !q.data || q.data.setups.length === 0 ? (
          <Card>
            <CardContent className="p-6 text-sm text-muted-foreground">
              Nessun setup in formazione al momento. Vengono ricalcolati a ogni scan —
              se hai appena aggiunto la funzione, i primi compaiono dopo la prossima
              scansione notturna.
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-2">
            {q.data.setups.map((s) => (
              <SetupRow key={s.id} setup={s} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
