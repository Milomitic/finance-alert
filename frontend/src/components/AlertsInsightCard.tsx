import { Gauge, Layers, Network, Swords, TrendingDown, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";

import type { Confluence } from "@/api/alerts";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { getAlertKindMeta } from "@/lib/alertMeta";
import { cn } from "@/lib/utils";

/* ─── AlertsInsightCard ──────────────────────────────────────────────────
 * Confluence digest above the alerts table.
 *
 *   - Top strip: the strongest long + short cluster (directional extremes).
 *   - Left:  Top 10 per forza — strongest multi-signal agreement (ranking).
 *   - Right: aggregate posture — long/short split, key counts, plus the
 *            horizon mix and which detectors are driving the confluences.
 *
 * Every lens derives from the SAME `clusters` payload (one fetch). */

const HZ_LABEL: Record<string, string> = { short: "Breve", medium: "Medio", long: "Lungo" };
const HZ_ORDER = ["short", "medium", "long"] as const;

/** Compact per-horizon letter chip (B/M/L) for the Top-10 Orizzonte column.
 *  Plain string-literal classes so Tailwind's purger keeps them. */
const HZ_CHIP: Record<string, { letter: string; label: string; cls: string }> = {
  short:  { letter: "B", label: "Breve", cls: "bg-violet-100 text-violet-700 dark:bg-violet-950/50 dark:text-violet-300" },
  medium: { letter: "M", label: "Medio", cls: "bg-sky-100 text-sky-700 dark:bg-sky-950/50 dark:text-sky-300" },
  long:   { letter: "L", label: "Lungo", cls: "bg-teal-100 text-teal-700 dark:bg-teal-950/50 dark:text-teal-300" },
};

function HorizonChips({ horizons }: { horizons: string[] }) {
  const ordered = HZ_ORDER.filter((h) => horizons.includes(h));
  if (ordered.length === 0) return <span className="text-muted-foreground/50">—</span>;
  return (
    <div className="flex gap-0.5">
      {ordered.map((h) => (
        <span key={h} className={cn("px-1 rounded text-[10px] font-bold leading-tight", HZ_CHIP[h].cls)} title={HZ_CHIP[h].label}>
          {HZ_CHIP[h].letter}
        </span>
      ))}
    </div>
  );
}

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

/* Rounded strength bar: muted track + direction-tinted gradient fill. */
function StrengthBar({ value, bull, width = "w-16" }: { value: number; bull: boolean; width?: string }) {
  const pct = Math.max(2, Math.min(100, value));
  return (
    <div className={cn("h-2 rounded-full bg-muted/70 overflow-hidden", width)}>
      <div
        className={cn("h-full rounded-full bg-gradient-to-r", bull ? "from-emerald-400 to-emerald-600" : "from-rose-400 to-rose-600")}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

/** Column header for the Top-10 table — fixed widths match TopRow's cells so
 *  the columns line up (the Titolo cell is flex-1 in both). */
function TopHeader() {
  return (
    <div className="flex items-center gap-2 px-2 pb-1.5 mb-1 border-b border-border/40 text-[10px] uppercase tracking-wider text-muted-foreground/70 font-semibold">
      <span className="w-4 shrink-0" />
      <span className="flex-1 min-w-0">Titolo</span>
      <span className="w-[4.25rem] shrink-0">Tono</span>
      <span className="w-12 shrink-0" title="Orizzonti coinvolti">Orizz.</span>
      <span className="w-9 shrink-0 text-right" title="Forza del segnale più forte del cluster">Forza max</span>
      <span className="w-8 shrink-0 text-right" title="Numero di segnali concordi">Seg</span>
      <span className="w-[5.25rem] shrink-0 text-right" title="Forza aggregata della confluenza">Forza</span>
    </div>
  );
}

function TopRow({ c, rank }: { c: Confluence; rank: number }) {
  const pct = Math.round(c.strength);
  const bull = c.direction === "bull";
  // Strongest component's Forza (prefer `strength`, legacy fallback `confidence`).
  const top = c.components[0];
  const maxForza =
    top != null && (top.strength != null || top.confidence != null)
      ? Math.round(top.strength ?? top.confidence)
      : null;
  return (
    <li>
      <Link
        to={`/stocks/${encodeURIComponent(c.ticker)}`}
        className="flex items-center gap-2 px-2 py-1 rounded-md hover:bg-accent/50 transition-colors min-w-0"
        title={`${c.name ?? c.ticker} · forza confluenza ${pct} · forza max ${maxForza ?? "—"} · ${c.n_signals} segnali${c.multi_horizon ? " · multi-orizzonte" : ""}${c.contested ? " · conteso" : ""}`}
      >
        <span className="w-4 shrink-0 text-right text-xs font-mono tabular-nums text-muted-foreground/60">{rank}</span>
        {/* Titolo — logo + ticker + name in ONE flex-1 cell so the meta columns
            align with the header. */}
        <div className="flex-1 min-w-0 flex items-center gap-2">
          <StockLogo ticker={c.ticker} size="xs" />
          <div className="min-w-0">
            <div className="text-sm font-bold tabular-nums leading-tight">{c.ticker}</div>
            {c.name && (
              <div className="text-[11px] text-muted-foreground truncate leading-tight" title={c.name}>{c.name}</div>
            )}
          </div>
        </div>
        {/* Tono (+ contested flag) */}
        <div className="w-[4.25rem] shrink-0 flex items-center gap-1">
          <DirPill direction={c.direction} />
          {c.contested && <Swords className="h-3 w-3 shrink-0 text-amber-500" aria-label="Conteso" />}
        </div>
        {/* Orizzonte span */}
        <div className="w-12 shrink-0"><HorizonChips horizons={c.horizons} /></div>
        {/* Forza max (strongest component) */}
        <span className="w-9 shrink-0 text-right text-xs font-semibold tabular-nums text-muted-foreground">
          {maxForza ?? "—"}
        </span>
        {/* Segnali */}
        <span className="w-8 shrink-0 text-right text-[11px] text-muted-foreground/80 tabular-nums">{c.n_signals}</span>
        {/* Forza (bar + value) */}
        <div className="w-[5.25rem] shrink-0 flex items-center justify-end gap-1.5">
          <StrengthBar value={pct} bull={bull} width="w-12" />
          <span className="text-sm font-semibold tabular-nums w-7 text-right">{pct}</span>
        </div>
      </Link>
    </li>
  );
}

/* Directional extreme — the strongest cluster on one side. Compact bordered
   cell for the top strip. */
function ExtremeCell({ label, c }: { label: string; c: Confluence | undefined }) {
  if (!c) {
    return (
      <div className="flex items-center gap-2 rounded-lg border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
        <span className="uppercase tracking-wider text-[11px]">{label}</span>
        <span className="ml-auto">—</span>
      </div>
    );
  }
  const bull = c.direction === "bull";
  return (
    <Link
      to={`/stocks/${encodeURIComponent(c.ticker)}`}
      className="flex items-center gap-2 rounded-lg border bg-muted/30 px-3 py-2 hover:bg-accent/40 transition-colors min-w-0"
      title={`${c.ticker} · forza ${Math.round(c.strength)} · ${c.n_signals} segnali`}
    >
      <span className="uppercase tracking-wider text-[11px] text-muted-foreground shrink-0">{label}</span>
      <StockLogo ticker={c.ticker} size="xs" />
      <span className="font-bold text-sm shrink-0">{c.ticker}</span>
      {c.name && <span className="text-[11px] text-muted-foreground truncate min-w-0">{c.name}</span>}
      <DirPill direction={c.direction} className="ml-auto" />
      <span className={cn("font-bold tabular-nums shrink-0", bull ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400")}>
        {Math.round(c.strength)}
      </span>
    </Link>
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
      <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-muted-foreground/80">
        <Icon className="h-3.5 w-3.5" />
        <span className="truncate">{label}</span>
      </div>
      <div className={cn("text-xl font-bold tabular-nums leading-tight mt-0.5", tone)}>{value}</div>
    </div>
  );
}

function SubHeader({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-xs uppercase tracking-wider text-muted-foreground font-semibold mb-1.5 flex items-center gap-2">
      <span className="shrink-0">{children}</span>
      <span className="h-px flex-1 bg-border/60" />
    </div>
  );
}

/* Horizon mix: how many clusters involve each timeframe (multi-horizon
   clusters count in several) — "trigger di breve vs struttura di lungo". */
function HorizonMix({ clusters }: { clusters: Confluence[] }) {
  const counts: Record<string, number> = { short: 0, medium: 0, long: 0 };
  for (const c of clusters) for (const h of c.horizons) if (h in counts) counts[h] += 1;
  const max = Math.max(1, ...HZ_ORDER.map((h) => counts[h]));
  return (
    <div className="space-y-1.5">
      {HZ_ORDER.map((h) => (
        <div key={h} className="flex items-center gap-2 text-[13px]">
          <span className="w-14 shrink-0 text-muted-foreground">{HZ_LABEL[h]}</span>
          <div className="flex-1 h-2 rounded-full bg-muted/70 overflow-hidden">
            <div className="h-full rounded-full bg-indigo-400 dark:bg-indigo-500" style={{ width: `${(counts[h] / max) * 100}%` }} />
          </div>
          <span className="w-7 shrink-0 text-right font-semibold tabular-nums">{counts[h]}</span>
        </div>
      ))}
    </div>
  );
}

/* Top-5 detectors by how many confluence components they contribute. */
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
          <div key={kind} className="flex items-center gap-2 text-[13px]">
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
          <>
            {/* Directional extremes — both on one row, top-left. */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-3xl mb-4">
              <ExtremeCell label="Top long" c={bull[0]} />
              <ExtremeCell label="Top short" c={bear[0]} />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-7 gap-y-5 items-stretch">
              {/* Col 1 — Top 10 by strength (logo + ticker + name) */}
              <div className="min-w-0">
                <SubHeader>Top 10 per forza</SubHeader>
                <TopHeader />
                <ul className="space-y-0.5">
                  {top10.map((c, i) => (
                    <TopRow key={`${c.ticker}-${c.direction}`} c={c} rank={i + 1} />
                  ))}
                </ul>
              </div>

              {/* Col 2 — aggregate posture */}
              <div className="min-w-0 md:border-l md:border-border/50 md:pl-7 space-y-4">
                <div>
                  <SubHeader>Posizionamento</SubHeader>
                  {/* Each label spans (and centers over) its own bar segment. */}
                  <div className="flex text-[13px] mb-1">
                    <span
                      className="text-center font-semibold text-emerald-600 dark:text-emerald-400 whitespace-nowrap"
                      style={{ width: `${bullPct}%` }}
                    >
                      {nBull} long · {bullPct}%
                    </span>
                    <span
                      className="text-center font-semibold text-rose-600 dark:text-rose-400 whitespace-nowrap"
                      style={{ width: `${100 - bullPct}%` }}
                    >
                      {100 - bullPct}% · {nBear} short
                    </span>
                  </div>
                  <div className="flex h-2.5 rounded-full overflow-hidden bg-muted">
                    <div className="bg-emerald-500" style={{ width: `${bullPct}%` }} />
                    <div className="bg-rose-500" style={{ width: `${100 - bullPct}%` }} />
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-2">
                  <StatCell icon={Layers} label="Multi-orizz." value={String(multiH)} tone={multiH > 0 ? "text-indigo-600 dark:text-indigo-400" : undefined} />
                  <StatCell icon={Swords} label="Contese" value={String(contested)} tone={contested > 0 ? "text-amber-600 dark:text-amber-400" : undefined} />
                  <StatCell icon={Gauge} label="Forza media" value={String(avgStrength)} />
                </div>

                {/* Horizon mix + detector mix — two columns on the same row. */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-5 gap-y-3">
                  <div>
                    <SubHeader>Orizzonti coinvolti</SubHeader>
                    <HorizonMix clusters={clusters} />
                  </div>
                  <div>
                    <SubHeader>Detector più attivi</SubHeader>
                    <DetectorMix clusters={clusters} />
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
