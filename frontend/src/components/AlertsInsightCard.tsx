import { Gauge, Layers, Network, Swords, TrendingDown, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";

import type { Confluence } from "@/api/alerts";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { getAlertKindMeta } from "@/lib/alertMeta";
import { cn } from "@/lib/utils";

/* ─── AlertsInsightCard ──────────────────────────────────────────────────
 * Two-column confluence digest above the alerts table (replaced the old
 * list/confluence view toggle).
 *
 *   Col 1 — Top 10 per forza: which tickers have the strongest multi-signal
 *           agreement (the ranking lens).
 *   Col 2 — Posizionamento: long/short split, key counts, the strongest
 *           cluster per side, the horizon mix, and which detectors are
 *           actually driving the current confluences (the aggregate lens).
 *
 * Both lenses derive from the SAME `clusters` payload (one fetch). */

const HZ_LABEL: Record<string, string> = { short: "Breve", medium: "Medio", long: "Lungo" };
const HZ_ORDER = ["short", "medium", "long"] as const;

function DirPill({ direction, className }: { direction: string; className?: string }) {
  const bull = direction === "bull";
  const Icon = bull ? TrendingUp : TrendingDown;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide shrink-0",
        bull
          ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300"
          : "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300",
        className,
      )}
    >
      <Icon className="h-2.5 w-2.5" />
      {bull ? "Long" : "Short"}
    </span>
  );
}

/* Rounded strength bar with a muted track + direction-tinted gradient fill. */
function StrengthBar({ value, bull, width = "w-20" }: { value: number; bull: boolean; width?: string }) {
  const pct = Math.max(2, Math.min(100, value));
  return (
    <div className={cn("h-2 rounded-full bg-muted/70 overflow-hidden", width)}>
      <div
        className={cn(
          "h-full rounded-full bg-gradient-to-r",
          bull ? "from-emerald-400 to-emerald-600" : "from-rose-400 to-rose-600",
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function TopRow({ c, rank }: { c: Confluence; rank: number }) {
  const pct = Math.round(c.strength);
  const bull = c.direction === "bull";
  return (
    <li>
      <Link
        to={`/stocks/${encodeURIComponent(c.ticker)}`}
        className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-accent/50 transition-colors min-w-0"
        title={`${c.name ?? c.ticker} · forza ${pct} · ${c.n_signals} segnali${c.multi_horizon ? " · multi-orizzonte" : ""}${c.contested ? " · conteso" : ""}`}
      >
        <span className="w-4 shrink-0 text-right text-[11px] font-mono tabular-nums text-muted-foreground/60">{rank}</span>
        <span className="font-bold text-sm shrink-0">{c.ticker}</span>
        <DirPill direction={c.direction} />
        {c.multi_horizon && <Layers className="h-3 w-3 shrink-0 text-indigo-500" aria-label="Multi-orizzonte" />}
        {c.contested && <Swords className="h-3 w-3 shrink-0 text-amber-500" aria-label="Conteso" />}
        <span className="text-[10px] text-muted-foreground/80 shrink-0 ml-0.5 tabular-nums">{c.n_signals} seg.</span>
        <div className="ml-auto flex items-center gap-2 shrink-0">
          <StrengthBar value={pct} bull={bull} />
          <span className="text-xs font-semibold tabular-nums w-7 text-right">{pct}</span>
        </div>
      </Link>
    </li>
  );
}

function StatCell({ icon: Icon, label, value, tone }: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="rounded-lg border bg-muted/30 px-2.5 py-2">
      <div className="flex items-center gap-1 text-[9.5px] uppercase tracking-wider text-muted-foreground/80">
        <Icon className="h-3 w-3" />
        <span className="truncate">{label}</span>
      </div>
      <div className={cn("text-lg font-bold tabular-nums leading-tight mt-0.5", tone)}>{value}</div>
    </div>
  );
}

function SubHeader({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-1.5 flex items-center gap-2">
      <span className="shrink-0">{children}</span>
      <span className="h-px flex-1 bg-border/60" />
    </div>
  );
}

function StrongestRow({ label, c }: { label: string; c: Confluence | undefined }) {
  if (!c) return null;
  const bull = c.direction === "bull";
  return (
    <Link
      to={`/stocks/${encodeURIComponent(c.ticker)}`}
      className="flex items-center gap-2 text-xs px-1.5 py-1 rounded-md hover:bg-accent/50"
      title={`${c.ticker} · forza ${Math.round(c.strength)} · ${c.n_signals} segnali`}
    >
      <span className="text-muted-foreground shrink-0 w-16">{label}</span>
      <span className="font-bold shrink-0">{c.ticker}</span>
      <DirPill direction={c.direction} />
      <span className={cn("ml-auto font-semibold tabular-nums", bull ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400")}>
        {Math.round(c.strength)}
      </span>
    </Link>
  );
}

/* Horizon mix: how many clusters involve each timeframe (a multi-horizon
   cluster counts in several). A quick read of "are these confluences
   short-term triggers or long-term structure?". */
function HorizonMix({ clusters }: { clusters: Confluence[] }) {
  const counts: Record<string, number> = { short: 0, medium: 0, long: 0 };
  for (const c of clusters) for (const h of c.horizons) if (h in counts) counts[h] += 1;
  const max = Math.max(1, ...HZ_ORDER.map((h) => counts[h]));
  return (
    <div className="space-y-1.5">
      {HZ_ORDER.map((h) => (
        <div key={h} className="flex items-center gap-2 text-xs">
          <span className="w-12 shrink-0 text-muted-foreground">{HZ_LABEL[h]}</span>
          <div className="flex-1 h-2 rounded-full bg-muted/70 overflow-hidden">
            <div className="h-full rounded-full bg-indigo-400 dark:bg-indigo-500" style={{ width: `${(counts[h] / max) * 100}%` }} />
          </div>
          <span className="w-7 shrink-0 text-right font-semibold tabular-nums">{counts[h]}</span>
        </div>
      ))}
    </div>
  );
}

/* Which detectors are driving the current confluences (top 5 by how many
   confluence components they contribute). Surfaces "what kind of agreement"
   is forming right now. */
function DetectorMix({ clusters }: { clusters: Confluence[] }) {
  const counts = new Map<string, number>();
  for (const c of clusters) for (const comp of c.components) {
    counts.set(comp.rule_kind, (counts.get(comp.rule_kind) ?? 0) + 1);
  }
  const top = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);
  if (top.length === 0) return null;
  const max = Math.max(1, ...top.map(([, n]) => n));
  return (
    <div className="space-y-1.5">
      {top.map(([kind, n]) => {
        const meta = getAlertKindMeta(kind);
        const Icon = meta.icon;
        return (
          <div key={kind} className="flex items-center gap-2 text-xs">
            <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            <span className="w-28 shrink-0 truncate" title={meta.label}>{meta.label}</span>
            <div className="flex-1 h-2 rounded-full bg-muted/70 overflow-hidden">
              <div className="h-full rounded-full bg-sky-400 dark:bg-sky-500" style={{ width: `${(n / max) * 100}%` }} />
            </div>
            <span className="w-7 shrink-0 text-right font-semibold tabular-nums">{n}</span>
          </div>
        );
      })}
    </div>
  );
}

export function AlertsInsightCard({ clusters, loading }: { clusters: Confluence[]; loading?: boolean }) {
  // Backend returns clusters sorted by strength desc.
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
        <SectionTitle icon={Network} label={`Confluenze attive (${clusters.length})`} className="mb-3" />
        {loading ? (
          <div className="py-8 text-center text-sm text-muted-foreground">Caricamento…</div>
        ) : clusters.length === 0 ? (
          <div className="py-8 text-center text-sm text-muted-foreground">
            Nessuna confluenza attiva: servono almeno 2 segnali concordi sullo stesso titolo.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-7 gap-y-5">
            {/* ── Col 1 — Top 10 by strength ─────────────────────────── */}
            <div className="min-w-0">
              <SubHeader>Top 10 per forza</SubHeader>
              <ul className="space-y-0.5">
                {top10.map((c, i) => (
                  <TopRow key={`${c.ticker}-${c.direction}`} c={c} rank={i + 1} />
                ))}
              </ul>
            </div>

            {/* ── Col 2 — Aggregate posture ──────────────────────────── */}
            <div className="min-w-0 md:border-l md:border-border/50 md:pl-7 space-y-4">
              {/* Long vs short split */}
              <div>
                <SubHeader>Posizionamento</SubHeader>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span className="font-semibold text-emerald-600 dark:text-emerald-400">{nBull} long · {bullPct}%</span>
                  <span className="font-semibold text-rose-600 dark:text-rose-400">{100 - bullPct}% · {nBear} short</span>
                </div>
                <div className="flex h-2.5 rounded-full overflow-hidden bg-muted">
                  <div className="bg-emerald-500" style={{ width: `${bullPct}%` }} />
                  <div className="bg-rose-500" style={{ width: `${100 - bullPct}%` }} />
                </div>
              </div>

              {/* Key counts */}
              <div className="grid grid-cols-3 gap-2">
                <StatCell icon={Layers} label="Multi-orizz." value={String(multiH)}
                  tone={multiH > 0 ? "text-indigo-600 dark:text-indigo-400" : undefined} />
                <StatCell icon={Swords} label="Contese" value={String(contested)}
                  tone={contested > 0 ? "text-amber-600 dark:text-amber-400" : undefined} />
                <StatCell icon={Gauge} label="Forza media" value={String(avgStrength)} />
              </div>

              {/* Strongest per side */}
              <div>
                <SubHeader>Estremi direzionali</SubHeader>
                <div className="space-y-0.5">
                  <StrongestRow label="Top long" c={bull[0]} />
                  <StrongestRow label="Top short" c={bear[0]} />
                </div>
              </div>

              {/* Horizon mix */}
              <div>
                <SubHeader>Orizzonti coinvolti</SubHeader>
                <HorizonMix clusters={clusters} />
              </div>

              {/* Detector mix */}
              <div>
                <SubHeader>Detector più attivi</SubHeader>
                <DetectorMix clusters={clusters} />
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
