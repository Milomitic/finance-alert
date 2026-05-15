import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { CheckCircle2, AlertTriangle, XCircle, Circle, Activity } from "lucide-react";
import type { DataSourceMetric } from "@/api/platformHealth";

type Props = {
  metrics: DataSourceMetric[];
  yfinanceBreaker: Record<string, unknown>;
};

const HEALTH_BADGE: Record<
  string,
  {
    label: string;
    classes: string;
    Icon: React.ComponentType<{ className?: string }>;
  }
> = {
  healthy: {
    label: "Operational",
    classes: "bg-emerald-50 text-emerald-700 border-emerald-200",
    Icon: CheckCircle2,
  },
  degraded: {
    label: "Degraded",
    classes: "bg-amber-50 text-amber-700 border-amber-200",
    Icon: AlertTriangle,
  },
  failing: {
    label: "Major outage",
    classes: "bg-red-50 text-red-700 border-red-200",
    Icon: XCircle,
  },
  idle: {
    label: "Idle",
    classes: "bg-slate-50 text-slate-600 border-slate-200",
    Icon: Circle,
  },
};

const ROLE_LABEL: Record<string, string> = {
  primary: "Primaria",
  fallback: "Fallback",
  scheduled: "Scheduled",
};

const ROLE_TONE: Record<string, string> = {
  primary: "bg-sky-50 text-sky-700 border-sky-200",
  fallback: "bg-violet-50 text-violet-700 border-violet-200",
  scheduled: "bg-slate-100 text-slate-700 border-slate-200",
};

function ago(ts: number | null): string {
  if (ts == null) return "—";
  const s = Math.floor(Date.now() / 1000 - ts);
  if (s < 60) return `${s}s fa`;
  if (s < 3600) return `${Math.floor(s / 60)}m fa`;
  if (s < 86400) return `${Math.floor(s / 3600)}h fa`;
  return `${Math.floor(s / 86400)}g fa`;
}

function RateLimitBar({
  used,
  limit,
  unit,
}: {
  used: number;
  limit: number;
  unit: string;
}) {
  const pct = Math.min(100, (used / limit) * 100);
  const tone =
    pct >= 90 ? "bg-red-500" : pct >= 70 ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[11px] text-muted-foreground">
        <span>Quota {unit}</span>
        <span className="tabular-nums">
          <span className="font-medium text-foreground">{used}</span> / {limit}
        </span>
      </div>
      <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
        <div
          className={`h-full ${tone} transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function SourceRow({ m }: { m: DataSourceMetric }) {
  const badge = HEALTH_BADGE[m.health] ?? HEALTH_BADGE.idle;
  const total = m.success + m.failure;
  const showRate = m.success_rate >= 0;
  return (
    <div className="flex flex-col gap-1.5 py-3 px-4 border-b last:border-b-0 hover:bg-muted/30 transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className="font-medium text-sm truncate"
              title={m.notes || m.label}
            >
              {m.label}
            </span>
            <span
              className={`px-1.5 py-0.5 text-[10px] font-medium rounded border ${
                ROLE_TONE[m.role] ?? ROLE_TONE.primary
              }`}
            >
              {ROLE_LABEL[m.role] ?? m.role}
            </span>
          </div>
          <div className="text-xs text-muted-foreground mt-1 tabular-nums">
            {total > 0 ? (
              <>
                <span className="text-emerald-700 font-medium">{m.success}</span>
                <span className="mx-0.5">OK</span>
                {m.failure > 0 && (
                  <>
                    {" · "}
                    <span className="text-red-700 font-medium">{m.failure}</span>
                    <span className="mx-0.5">KO</span>
                  </>
                )}
                {showRate && (
                  <>
                    {" · "}
                    {(m.success_rate * 100).toFixed(1)}%
                  </>
                )}
                {m.last_success_at && (
                  <>
                    {" · ultimo "}
                    {ago(m.last_success_at)}
                  </>
                )}
              </>
            ) : (
              <span className="italic">Nessuna chiamata recente</span>
            )}
          </div>
        </div>
        <span
          className={`inline-flex items-center gap-1 px-2.5 py-0.5 text-[11px] font-medium rounded-full border shrink-0 ${badge.classes}`}
        >
          <badge.Icon className="h-3 w-3" />
          {badge.label}
        </span>
      </div>

      {/* Rate-limit usage bars, only if the source declared a free-tier limit */}
      {m.per_minute_limit != null && (
        <RateLimitBar
          used={m.calls_last_minute ?? 0}
          limit={m.per_minute_limit}
          unit="/ min"
        />
      )}
      {m.per_day_limit != null && (
        <RateLimitBar
          used={m.calls_last_day ?? 0}
          limit={m.per_day_limit}
          unit="/ giorno"
        />
      )}

      {m.last_failure_reason && m.health !== "healthy" && (
        <div
          className="text-[11px] text-red-700/80 truncate font-mono"
          title={m.last_failure_reason}
        >
          ✗ {m.last_failure_reason}
        </div>
      )}
    </div>
  );
}

// Op (= service) labels in Italian. Ordered the way they appear in the
// catalog so the visual ordering mirrors KNOWN_SOURCES.
const OP_LABEL: Record<string, string> = {
  ohlcv: "Prezzi storici (OHLCV)",
  fundamentals: "Fondamentali (income, info)",
  market_cap: "Capitalizzazione",
  live_quote: "Quote real-time",
  news: "News",
  earnings: "Earnings",
  macro: "Macro (FRED)",
  consensus: "Consensus macro",
  filings: "Filings 13F",
};

// Pick the rolled-up health for a group of sources covering the same op:
//   any healthy → covered & operational
//   all failing → outage on that service
//   anything else (mixed) → degraded
function rollupHealth(sources: DataSourceMetric[]): "healthy" | "degraded" | "failing" | "idle" {
  if (sources.length === 0) return "idle";
  const hasHealthy = sources.some((s) => s.health === "healthy");
  const allFailing = sources.every((s) => s.health === "failing");
  if (hasHealthy) return "healthy";
  if (allFailing) return "failing";
  return "degraded";
}

const ROLLUP_BADGE: Record<string, { label: string; classes: string }> = {
  healthy: {
    label: "Operational",
    classes: "bg-emerald-50 text-emerald-700 border-emerald-200",
  },
  degraded: {
    label: "Degraded",
    classes: "bg-amber-50 text-amber-700 border-amber-200",
  },
  failing: {
    label: "Major outage",
    classes: "bg-red-50 text-red-700 border-red-200",
  },
  idle: {
    label: "Idle",
    classes: "bg-slate-50 text-slate-600 border-slate-200",
  },
};

export default function DataSourcesCard({ metrics, yfinanceBreaker }: Props) {
  const breakerState = String(yfinanceBreaker.state ?? "closed").toLowerCase();
  const breakerOpen = breakerState === "open" || breakerState === "half_open";

  // Group by op (= service), preserving the catalog's natural ordering.
  // `Object.entries` on a string-keyed object iterates in insertion order
  // in modern JS engines, which means the first source seen for an op
  // determines that op's slot in the rendered list.
  const groups = new Map<string, DataSourceMetric[]>();
  for (const m of metrics) {
    const arr = groups.get(m.op);
    if (arr) arr.push(m);
    else groups.set(m.op, [m]);
  }

  const totalServices = groups.size;
  const failingServices = Array.from(groups.values()).filter(
    (sources) => rollupHealth(sources) === "failing"
  ).length;
  const operationalServices = Array.from(groups.values()).filter(
    (sources) => rollupHealth(sources) === "healthy"
  ).length;

  return (
    <Card className="h-full overflow-hidden">
      <CardHeader className="pb-3 border-b bg-muted/20">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base font-semibold flex items-center gap-1.5">
            <Activity className="h-4 w-4" />
            Servizi dati
            <span className="text-[11px] font-normal text-muted-foreground ml-1 tabular-nums">
              {operationalServices}/{totalServices} operativi
            </span>
          </CardTitle>
          <span
            className={`inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-medium rounded-full border ${
              breakerOpen
                ? "bg-red-50 text-red-700 border-red-200"
                : "bg-emerald-50 text-emerald-700 border-emerald-200"
            }`}
            title="yfinance circuit breaker"
          >
            {breakerOpen ? <XCircle className="h-3 w-3" /> : <CheckCircle2 className="h-3 w-3" />}
            Breaker {breakerState}
          </span>
        </div>
        {failingServices > 0 && (
          <div className="text-xs text-red-700 mt-1">
            ⚠ {failingServices} servizi{failingServices === 1 ? "o" : ""} in errore —
            tutte le fonti che li alimentano stanno fallendo
          </div>
        )}
      </CardHeader>
      <CardContent className="p-0 max-h-[480px] overflow-auto">
        {Array.from(groups.entries()).map(([op, sources]) => {
          const rollup = rollupHealth(sources);
          const badge = ROLLUP_BADGE[rollup];
          const opLabel = OP_LABEL[op] ?? op;
          const singleSource = sources.length === 1;
          return (
            <div key={op}>
              <div className="px-4 py-2 bg-muted/40 border-b flex items-center justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="text-[12px] font-semibold tracking-tight">
                    {opLabel}
                  </div>
                  <div className="text-[10.5px] text-muted-foreground mt-0.5">
                    {sources.length} font{sources.length === 1 ? "e" : "i"}
                    {singleSource && (
                      <span
                        className="ml-1.5 text-amber-700"
                        title="Questo servizio dipende da una singola fonte: se cade non c'è fallback"
                      >
                        · single-source
                      </span>
                    )}
                  </div>
                </div>
                <span
                  className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10.5px] font-medium rounded-full border shrink-0 ${badge.classes}`}
                >
                  {badge.label}
                </span>
              </div>
              {sources.map((m) => (
                <SourceRow key={`${m.source}.${m.op}`} m={m} />
              ))}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
