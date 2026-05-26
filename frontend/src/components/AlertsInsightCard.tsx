import { Layers, Network, Swords, TrendingDown, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";

import type { Confluence } from "@/api/alerts";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { cn } from "@/lib/utils";

/* ─── AlertsInsightCard ──────────────────────────────────────────────────
 * A two-column confluence digest that sits between the filters and the
 * alerts table. It replaces the old list/confluence VIEW TOGGLE — instead
 * of swapping the whole table out, the confluence intelligence is always
 * visible alongside the list.
 *
 *   Col 1 — Top 10 per forza: which tickers have the strongest multi-signal
 *           agreement (the ranking lens).
 *   Col 2 — Posizionamento: bull-vs-bear cluster split + multi-horizon /
 *           contested counts + the strongest cluster on each side (the
 *           aggregate-posture lens).
 *
 * Both derive from the SAME `clusters` payload (one fetch, two views). */

const HZ_LABEL: Record<string, string> = { short: "breve", medium: "medio", long: "lungo" };

function DirPill({ direction }: { direction: string }) {
  const bull = direction === "bull";
  const Icon = bull ? TrendingUp : TrendingDown;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide shrink-0",
        bull
          ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300"
          : "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300",
      )}
    >
      <Icon className="h-2.5 w-2.5" />
      {bull ? "Long" : "Short"}
    </span>
  );
}

function TopRow({ c, rank }: { c: Confluence; rank: number }) {
  const pct = Math.round(c.strength);
  const bull = c.direction === "bull";
  return (
    <li>
      <Link
        to={`/stocks/${encodeURIComponent(c.ticker)}`}
        className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-accent/40 transition-colors min-w-0"
        title={c.name ?? c.ticker}
      >
        <span className="w-4 shrink-0 text-right text-[11px] tabular-nums text-muted-foreground">{rank}</span>
        <span className="font-bold text-sm shrink-0">{c.ticker}</span>
        <DirPill direction={c.direction} />
        {c.multi_horizon && (
          <Layers
            className="h-3 w-3 shrink-0 text-indigo-500"
            aria-label="Multi-orizzonte"
          />
        )}
        {c.contested && (
          <Swords className="h-3 w-3 shrink-0 text-amber-500" aria-label="Conteso" />
        )}
        <span className="text-[10px] text-muted-foreground shrink-0 ml-0.5">{c.n_signals} seg.</span>
        <div className="ml-auto flex items-center gap-1.5 shrink-0">
          <div className="h-1.5 w-16 rounded-full bg-muted overflow-hidden">
            <div
              className={cn("h-full rounded-full", bull ? "bg-emerald-500" : "bg-rose-500")}
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className="text-xs font-semibold tabular-nums w-7 text-right">{pct}</span>
        </div>
      </Link>
    </li>
  );
}

function StatCell({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded border bg-muted/30 px-2.5 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground/80">{label}</div>
      <div className={cn("text-base font-bold tabular-nums", tone)}>{value}</div>
    </div>
  );
}

function StrongestRow({ label, c }: { label: string; c: Confluence | undefined }) {
  if (!c) return null;
  const bull = c.direction === "bull";
  return (
    <Link
      to={`/stocks/${encodeURIComponent(c.ticker)}`}
      className="flex items-center gap-2 text-xs px-2 py-1 rounded hover:bg-accent/40"
      title={`${c.ticker} · forza ${Math.round(c.strength)} · ${c.n_signals} segnali${c.multi_horizon ? ` · multi-orizzonte (${c.horizons.map((h) => HZ_LABEL[h] ?? h).join(" + ")})` : ""}`}
    >
      <span className="text-muted-foreground shrink-0">{label}</span>
      <span className="font-bold shrink-0">{c.ticker}</span>
      <DirPill direction={c.direction} />
      <span className={cn("ml-auto font-semibold tabular-nums", bull ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400")}>
        {Math.round(c.strength)}
      </span>
    </Link>
  );
}

export function AlertsInsightCard({
  clusters,
  loading,
}: {
  clusters: Confluence[];
  loading?: boolean;
}) {
  // Backend returns clusters sorted by strength desc, so slicing/filtering
  // preserves the "strongest first" order.
  const top10 = clusters.slice(0, 10);
  const bull = clusters.filter((c) => c.direction === "bull");
  const bear = clusters.filter((c) => c.direction === "bear");
  const nBull = bull.length;
  const nBear = bear.length;
  const nTot = nBull + nBear;
  const bullPct = nTot ? Math.round((nBull / nTot) * 100) : 0;
  const multiH = clusters.filter((c) => c.multi_horizon).length;
  const contested = clusters.filter((c) => c.contested).length;
  const avgStrength = clusters.length
    ? Math.round(clusters.reduce((s, c) => s + c.strength, 0) / clusters.length)
    : 0;

  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={Network}
          label={`Confluenze attive (${clusters.length})`}
          className="mb-3"
        />
        {loading ? (
          <div className="py-6 text-center text-sm text-muted-foreground">Caricamento…</div>
        ) : clusters.length === 0 ? (
          <div className="py-6 text-center text-sm text-muted-foreground">
            Nessuna confluenza attiva: servono almeno 2 segnali concordi sullo stesso titolo.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4">
            {/* Col 1 — Top 10 by strength */}
            <div className="min-w-0">
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-1.5">
                Top 10 per forza
              </div>
              <ul className="space-y-0.5">
                {top10.map((c, i) => (
                  <TopRow key={`${c.ticker}-${c.direction}`} c={c} rank={i + 1} />
                ))}
              </ul>
            </div>

            {/* Col 2 — Aggregate posture */}
            <div className="min-w-0 md:border-l md:border-border/50 md:pl-6 space-y-3">
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-1.5">
                Posizionamento
              </div>
              {/* Bull vs bear split bar */}
              <div>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                    {nBull} long
                  </span>
                  <span className="font-semibold text-rose-600 dark:text-rose-400">
                    short {nBear}
                  </span>
                </div>
                <div className="flex h-2 rounded-full overflow-hidden bg-muted">
                  <div className="bg-emerald-500" style={{ width: `${bullPct}%` }} />
                  <div className="bg-rose-500" style={{ width: `${100 - bullPct}%` }} />
                </div>
              </div>
              {/* Stat cells */}
              <div className="grid grid-cols-3 gap-2">
                <StatCell
                  label="Multi-orizz."
                  value={String(multiH)}
                  tone={multiH > 0 ? "text-indigo-600 dark:text-indigo-400" : undefined}
                />
                <StatCell
                  label="Contese"
                  value={String(contested)}
                  tone={contested > 0 ? "text-amber-600 dark:text-amber-400" : undefined}
                />
                <StatCell label="Forza media" value={String(avgStrength)} />
              </div>
              {/* Strongest on each side */}
              <div className="space-y-0.5 pt-1 border-t border-border/40">
                <StrongestRow label="Top long" c={bull[0]} />
                <StrongestRow label="Top short" c={bear[0]} />
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
