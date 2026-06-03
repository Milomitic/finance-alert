import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  AlertTriangle,
  Building2,
  CalendarClock,
  CandlestickChart,
  CheckCircle2,
  Circle,
  Database,
  FileSpreadsheet,
  Gavel,
  Globe,
  Newspaper,
  ShieldAlert,
  ShieldCheck,
  Sunrise,
  XCircle,
} from "lucide-react";
import type { DataSourceMetric } from "@/api/platformHealth";
import { cn } from "@/lib/utils";

type Props = {
  metrics: DataSourceMetric[];
  yfinanceBreaker: Record<string, unknown>;
  /** Clicking a source row scrolls to + filters the live-log table to it. */
  onSelectSource?: (label: string, tokens: string[]) => void;
};

type Health = "healthy" | "degraded" | "failing" | "idle";

/* ─── Fonti dati ──────────────────────────────────────────────────────
 *
 * Clustered health view of every data source. Sources are grouped by
 * WHAT THEY PROVIDE (a "tipologia"), not by which endpoint they hit — so
 * the three analyst feeds (Finnhub upgrades, Finnhub recommendation,
 * Nasdaq consensus) finally read as one "Analisti" cluster, the two
 * earnings providers as one "Earnings" cluster, etc. Each cluster shows
 * a glanceable visual (a dot per source) beside the textual list, and a
 * top summary strip rolls the whole fleet into a single segmented bar.
 */

const HEALTH_META: Record<
  Health,
  { label: string; dot: string; bar: string; chip: string; Icon: React.ComponentType<{ className?: string }> }
> = {
  healthy: {
    label: "Operativa",
    dot: "bg-emerald-500",
    bar: "bg-emerald-500",
    chip: "bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800/60",
    Icon: CheckCircle2,
  },
  degraded: {
    label: "Degradata",
    dot: "bg-amber-500",
    bar: "bg-amber-500",
    chip: "bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800/60",
    Icon: AlertTriangle,
  },
  failing: {
    label: "In errore",
    dot: "bg-rose-500",
    bar: "bg-rose-500",
    chip: "bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-800/60",
    Icon: XCircle,
  },
  idle: {
    label: "Inattiva",
    dot: "bg-slate-300 dark:bg-slate-600",
    bar: "bg-slate-300 dark:bg-slate-600",
    chip: "bg-slate-50 dark:bg-slate-800/60 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700",
    Icon: Circle,
  },
};

function normHealth(h: string): Health {
  return h === "healthy" || h === "degraded" || h === "failing" ? h : "idle";
}

const ROLE_LABEL: Record<string, string> = {
  primary: "Primaria",
  fallback: "Fallback",
  scheduled: "Pianificata",
};
const ROLE_TONE: Record<string, string> = {
  primary: "bg-sky-50 dark:bg-sky-950/40 text-sky-700 dark:text-sky-300 border-sky-200 dark:border-sky-800/60",
  fallback: "bg-violet-50 dark:bg-violet-950/40 text-violet-700 dark:text-violet-300 border-violet-200 dark:border-violet-800/60",
  scheduled: "bg-slate-100 dark:bg-slate-800/60 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700",
};

/* Cluster taxonomy. `ops` lists the data_source_metrics `op` values that
 * belong to each tipologia; the order here is the render order. */
type CatKey =
  | "market" | "fundamentals" | "news" | "analyst"
  | "earnings" | "macro" | "institutional" | "premarket" | "other";

const CATEGORIES: {
  key: CatKey;
  label: string;
  desc: string;
  Icon: React.ComponentType<{ className?: string }>;
  tint: string; // icon chip
  ops: string[];
}[] = [
  { key: "market", label: "Prezzi & quote", desc: "OHLCV · capitalizzazione · quote live",
    Icon: CandlestickChart, tint: "bg-sky-50 dark:bg-sky-950/40 text-sky-600 dark:text-sky-300 border-sky-200 dark:border-sky-800/60",
    ops: ["ohlcv", "market_cap", "live_quote"] },
  { key: "fundamentals", label: "Fondamentali", desc: "Income statement · info · micro-dati",
    Icon: FileSpreadsheet, tint: "bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-300 border-indigo-200 dark:border-indigo-800/60",
    ops: ["fundamentals"] },
  { key: "news", label: "News", desc: "Articoli e headline per ticker",
    Icon: Newspaper, tint: "bg-cyan-50 dark:bg-cyan-950/40 text-cyan-600 dark:text-cyan-300 border-cyan-200 dark:border-cyan-800/60",
    ops: ["news"] },
  { key: "analyst", label: "Analisti", desc: "Upgrade/downgrade · recommendation · target",
    Icon: Gavel, tint: "bg-violet-50 dark:bg-violet-950/40 text-violet-600 dark:text-violet-300 border-violet-200 dark:border-violet-800/60",
    ops: ["upgrades", "recommendation", "analyst"] },
  { key: "earnings", label: "Earnings", desc: "EPS / revenue: stime e dati effettivi",
    Icon: CalendarClock, tint: "bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800/60",
    ops: ["earnings"] },
  { key: "macro", label: "Macro", desc: "Serie FRED · consensus calendario",
    Icon: Globe, tint: "bg-amber-50 dark:bg-amber-950/40 text-amber-600 dark:text-amber-300 border-amber-200 dark:border-amber-800/60",
    ops: ["macro", "consensus"] },
  { key: "institutional", label: "Istituzionali", desc: "Filing 13F dei fondi",
    Icon: Building2, tint: "bg-rose-50 dark:bg-rose-950/40 text-rose-600 dark:text-rose-300 border-rose-200 dark:border-rose-800/60",
    ops: ["filings"] },
  { key: "premarket", label: "Pre-market", desc: "Volume di pre-apertura",
    Icon: Sunrise, tint: "bg-orange-50 dark:bg-orange-950/40 text-orange-600 dark:text-orange-300 border-orange-200 dark:border-orange-800/60",
    ops: ["premarket"] },
];

const OP_TO_CAT: Record<string, CatKey> = (() => {
  const m: Record<string, CatKey> = {};
  for (const c of CATEGORIES) for (const op of c.ops) m[op] = c.key;
  return m;
})();

const OTHER_CAT = {
  key: "other" as CatKey,
  label: "Altre fonti",
  desc: "Operazioni non ancora classificate",
  Icon: Database,
  tint: "bg-slate-50 dark:bg-slate-800/60 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700",
  ops: [] as string[],
};

function ago(ts: number | null): string {
  if (ts == null) return "—";
  const s = Math.floor(Date.now() / 1000 - ts);
  if (s < 60) return `${s}s fa`;
  if (s < 3600) return `${Math.floor(s / 60)}m fa`;
  if (s < 86400) return `${Math.floor(s / 3600)}h fa`;
  return `${Math.floor(s / 86400)}g fa`;
}

function rollup(sources: DataSourceMetric[]): Health {
  if (sources.length === 0) return "idle";
  if (sources.some((s) => normHealth(s.health) === "healthy")) return "healthy";
  if (sources.every((s) => normHealth(s.health) === "failing")) return "failing";
  if (sources.some((s) => normHealth(s.health) === "failing" || normHealth(s.health) === "degraded"))
    return "degraded";
  return "idle";
}

function RateLimitBar({ used, limit, unit }: { used: number; limit: number; unit: string }) {
  const pct = Math.min(100, (used / limit) * 100);
  const tone = pct >= 90 ? "bg-rose-500" : pct >= 70 ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div className="space-y-0.5">
      <div className="flex items-center justify-between text-[10px] text-muted-foreground">
        <span>Quota {unit}</span>
        <span className="tabular-nums">
          <span className="font-medium text-foreground">{used}</span> / {limit}
        </span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
        <div className={cn("h-full transition-all", tone)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

/* One source line inside a cluster card. Clickable when `onSelect` is
 * provided — scrolls to + filters the live-log table to this source. */
function SourceRow({
  m,
  onSelect,
}: {
  m: DataSourceMetric;
  onSelect?: (label: string, tokens: string[]) => void;
}) {
  const h = normHealth(m.health);
  const meta = HEALTH_META[h];
  const total = m.success + m.failure;
  const clickable = !!onSelect;
  // Explicit match tokens from the backend (fall back to the source key).
  const tokens = m.log_match && m.log_match.length ? m.log_match : [m.source];
  return (
    <div
      role={clickable ? "button" : undefined}
      tabIndex={clickable ? 0 : undefined}
      onClick={clickable ? () => onSelect!(m.source, tokens) : undefined}
      onKeyDown={
        clickable
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect!(m.source, tokens);
              }
            }
          : undefined
      }
      title={clickable ? `Filtra i log live su "${m.source}"` : undefined}
      className={cn(
        "px-3 py-2 border-t first:border-t-0 border-border/60 transition-colors",
        clickable
          ? "cursor-pointer hover:bg-sky-50/60 dark:hover:bg-sky-950/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/60 focus-visible:ring-inset"
          : "hover:bg-muted/30",
      )}
    >
      <div className="flex items-center gap-2 min-w-0">
        <span className={cn("h-2 w-2 rounded-full shrink-0", meta.dot)} title={meta.label} />
        <span className="text-[13px] font-medium truncate" title={m.notes || m.label}>
          {m.label}
        </span>
        <span
          className={cn(
            "ml-auto shrink-0 px-1.5 py-0.5 text-[9.5px] font-medium rounded border",
            ROLE_TONE[m.role] ?? ROLE_TONE.primary,
          )}
        >
          {ROLE_LABEL[m.role] ?? m.role}
        </span>
      </div>
      <div className="mt-0.5 pl-4 text-[11px] text-muted-foreground tabular-nums">
        {total > 0 ? (
          <>
            <span className="text-emerald-700 dark:text-emerald-400 font-medium">{m.success}</span> ok
            {m.failure > 0 && (
              <>
                {" · "}
                <span className="text-rose-700 dark:text-rose-400 font-medium">{m.failure}</span> ko
              </>
            )}
            {m.success_rate >= 0 && <> · {(m.success_rate * 100).toFixed(0)}%</>}
            {m.last_success_at && <> · {ago(m.last_success_at)}</>}
          </>
        ) : (
          <span className="italic">nessuna chiamata recente</span>
        )}
      </div>
      {(m.per_minute_limit != null || m.per_day_limit != null) && (
        <div className="mt-1.5 pl-4 space-y-1">
          {m.per_minute_limit != null && (
            <RateLimitBar used={m.calls_last_minute ?? 0} limit={m.per_minute_limit} unit="/ min" />
          )}
          {m.per_day_limit != null && (
            <RateLimitBar used={m.calls_last_day ?? 0} limit={m.per_day_limit} unit="/ giorno" />
          )}
        </div>
      )}
      {m.last_failure_reason && h !== "healthy" && (
        <div className="mt-1 pl-4 text-[10.5px] text-rose-700/80 dark:text-rose-400/80 truncate font-mono" title={m.last_failure_reason}>
          ✗ {m.last_failure_reason}
        </div>
      )}
    </div>
  );
}

/* A cluster (tipologia) card: icon + label + per-source dots (visual) +
 * the textual source list. */
function ClusterCard({
  cat,
  sources,
  index,
  onSelectSource,
}: {
  cat: (typeof CATEGORIES)[number] | typeof OTHER_CAT;
  sources: DataSourceMetric[];
  index: number;
  onSelectSource?: (label: string, tokens: string[]) => void;
}) {
  const roll = rollup(sources);
  const meta = HEALTH_META[roll];
  const single = sources.length === 1;
  return (
    <div
      className="rounded-xl border bg-card overflow-hidden flex flex-col animate-in fade-in-0 slide-in-from-bottom-2 fill-mode-both"
      style={{ animationDelay: `${index * 45}ms`, animationDuration: "320ms" }}
    >
      <div className="flex items-center gap-2.5 px-3 py-2.5 border-b bg-muted/20">
        <span className={cn("grid place-items-center h-8 w-8 rounded-lg border shrink-0", cat.tint)}>
          <cat.Icon className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-semibold tracking-tight truncate">{cat.label}</span>
            {single && (
              <span
                className="text-amber-600 shrink-0"
                title="Singola fonte: nessun fallback se cade"
              >
                <ShieldAlert className="h-3 w-3" />
              </span>
            )}
          </div>
          <div className="text-[10.5px] text-muted-foreground truncate" title={cat.desc}>
            {cat.desc}
          </div>
        </div>
        {/* Visual: a dot per source, colored by health. */}
        <div className="flex items-center gap-1 shrink-0" title={`${sources.length} fonti`}>
          {sources.map((s) => (
            <span
              key={`${s.source}.${s.op}`}
              className={cn("h-2 w-2 rounded-full", HEALTH_META[normHealth(s.health)].dot)}
            />
          ))}
        </div>
        <span
          className={cn(
            "shrink-0 inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium rounded-full border",
            meta.chip,
          )}
        >
          <meta.Icon className="h-3 w-3" />
          {meta.label}
        </span>
      </div>
      <div className="flex-1">
        {sources.map((m) => (
          <SourceRow key={`${m.source}.${m.op}`} m={m} onSelect={onSelectSource} />
        ))}
      </div>
    </div>
  );
}

/* The top "vista riassuntiva": stat tiles + a single segmented bar that
 * rolls the whole fleet into one glance. */
function SummaryStrip({
  counts,
  total,
}: {
  counts: Record<Health, number>;
  total: number;
}) {
  const order: Health[] = ["healthy", "degraded", "failing", "idle"];
  const tiles: { key: Health; label: string }[] = [
    { key: "healthy", label: "Operative" },
    { key: "degraded", label: "Degradate" },
    { key: "failing", label: "In errore" },
    { key: "idle", label: "Inattive" },
  ];
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {tiles.map((t) => {
          const meta = HEALTH_META[t.key];
          return (
            <div key={t.key} className="rounded-lg border bg-card px-3 py-2 flex items-center gap-2.5">
              <span className={cn("grid place-items-center h-8 w-8 rounded-lg border", meta.chip)}>
                <meta.Icon className="h-4 w-4" />
              </span>
              <div className="leading-tight">
                <div className="text-xl font-bold tabular-nums">{counts[t.key]}</div>
                <div className="text-[10.5px] text-muted-foreground">{t.label}</div>
              </div>
            </div>
          );
        })}
      </div>
      {/* Segmented health bar — the corresponding VISUAL of the textual list. */}
      <div>
        <div className="flex h-2.5 w-full rounded-full overflow-hidden bg-muted">
          {order.map((k) =>
            counts[k] > 0 ? (
              <div
                key={k}
                className={cn("h-full transition-all", HEALTH_META[k].bar)}
                style={{ width: `${(counts[k] / total) * 100}%` }}
                title={`${counts[k]} ${HEALTH_META[k].label.toLowerCase()}`}
              />
            ) : null,
          )}
        </div>
      </div>
    </div>
  );
}

/* ─── yfinance circuit-breaker chip ───────────────────────────────────
 *
 * Shows the breaker state and, when it's tripped, WHEN the block lifts.
 * The backend sends an absolute `blocked_until` (UTC epoch seconds); we
 * count down against it locally on a 1s tick so the figure stays accurate
 * between the 5s health polls (and doesn't freeze/jump). Half-open means
 * the cooldown already elapsed and a probe is mid-flight — there we show
 * the probe timeout instead. */
const BREAKER_LABEL: Record<string, string> = {
  closed: "chiuso",
  open: "aperto",
  half_open: "semi-aperto",
};

function fmtRemaining(sec: number): string {
  const s = Math.max(0, Math.ceil(sec));
  if (s >= 60) return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
  return `${s}s`;
}

function fmtClock(epochSec: number): string {
  return new Date(epochSec * 1000).toLocaleTimeString("it-IT", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function BreakerChip({ breaker }: { breaker: Record<string, unknown> }) {
  const state = String(breaker.state ?? "closed").toLowerCase();
  const isOpen = state === "open";
  const isHalfOpen = state === "half_open";
  const active = isOpen || isHalfOpen;

  // Local 1s ticker — only while the breaker is tripped — for a smooth
  // countdown that doesn't depend on the health-poll cadence.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [active]);

  const blockedUntil = typeof breaker.blocked_until === "number" ? breaker.blocked_until : null;
  const probeDeadline = typeof breaker.probe_deadline === "number" ? breaker.probe_deadline : null;
  const nowSec = now / 1000;

  // Tone: open → rose (blocked), half-open → amber (recovering/probing),
  // closed → emerald. Literal class strings so Tailwind's purger keeps them.
  const tone = isOpen
    ? "bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-800/60"
    : isHalfOpen
    ? "bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800/60"
    : "bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800/60";

  let detail: React.ReactNode = null;
  if (isOpen && blockedUntil != null) {
    const remaining = blockedUntil - nowSec;
    detail =
      remaining > 0 ? (
        <>
          {" · sblocco tra "}
          <span className="tabular-nums font-semibold">{fmtRemaining(remaining)}</span>
          {` (alle ${fmtClock(blockedUntil)})`}
        </>
      ) : (
        <> · sblocco imminente…</>
      );
  } else if (isHalfOpen) {
    const remaining = probeDeadline != null ? probeDeadline - nowSec : null;
    detail = (
      <>
        {" · verifica in corso"}
        {remaining != null && remaining > 0 && (
          <span className="tabular-nums"> (timeout {fmtRemaining(remaining)})</span>
        )}
      </>
    );
  }

  const Icon = active ? ShieldAlert : ShieldCheck;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-0.5 text-[11px] font-medium rounded-full border",
        tone,
      )}
      title="Circuit breaker yfinance — quando aperto, gli scan saltano il provider primario"
    >
      <Icon className="h-3.5 w-3.5" />
      Breaker yfinance: {BREAKER_LABEL[state] ?? state}
      {detail}
    </span>
  );
}

export default function DataSourcesCard({ metrics, yfinanceBreaker, onSelectSource }: Props) {
  // Bucket every metric into its cluster, preserving CATEGORIES order.
  const buckets = new Map<CatKey, DataSourceMetric[]>();
  for (const m of metrics) {
    const key = OP_TO_CAT[m.op] ?? "other";
    const arr = buckets.get(key);
    if (arr) arr.push(m);
    else buckets.set(key, [m]);
  }
  const ordered: { cat: (typeof CATEGORIES)[number] | typeof OTHER_CAT; sources: DataSourceMetric[] }[] = [];
  for (const cat of CATEGORIES) {
    const s = buckets.get(cat.key);
    if (s && s.length) ordered.push({ cat, sources: s });
  }
  const other = buckets.get("other");
  if (other && other.length) ordered.push({ cat: OTHER_CAT, sources: other });

  const counts: Record<Health, number> = { healthy: 0, degraded: 0, failing: 0, idle: 0 };
  for (const m of metrics) counts[normHealth(m.health)]++;
  const total = metrics.length || 1;
  const operational = counts.healthy;

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-3 border-b bg-muted/20">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <span className="grid place-items-center h-7 w-7 rounded-lg border bg-background">
              <Database className="h-4 w-4" />
            </span>
            Fonti dati
            <span className="text-[11px] font-normal text-muted-foreground tabular-nums">
              {operational}/{metrics.length} operative
            </span>
          </CardTitle>
          <BreakerChip breaker={yfinanceBreaker} />
        </div>
      </CardHeader>
      <CardContent className="p-4 space-y-4">
        {metrics.length === 0 ? (
          <div className="text-sm text-muted-foreground py-6 text-center">
            Nessuna chiamata registrata ancora. Le metriche si popolano dopo il primo
            scan / refresh fondamentali.
          </div>
        ) : (
          <>
            <SummaryStrip counts={counts} total={total} />
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {ordered.map(({ cat, sources }, i) => (
                <ClusterCard
                  key={cat.key}
                  cat={cat}
                  sources={sources}
                  index={i}
                  onSelectSource={onSelectSource}
                />
              ))}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
