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

export default function DataSourcesCard({ metrics, yfinanceBreaker }: Props) {
  const breakerState = String(yfinanceBreaker.state ?? "closed").toLowerCase();
  const breakerOpen = breakerState === "open" || breakerState === "half_open";

  // Group by role for visual hierarchy
  const groups: Record<string, DataSourceMetric[]> = {
    primary: [],
    fallback: [],
    scheduled: [],
  };
  for (const m of metrics) {
    const g = groups[m.role] ?? groups.primary;
    g.push(m);
  }

  const totalSources = metrics.length;
  const healthy = metrics.filter((m) => m.health === "healthy").length;
  const failing = metrics.filter((m) => m.health === "failing").length;

  return (
    <Card className="h-full overflow-hidden">
      <CardHeader className="pb-3 border-b bg-muted/20">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base font-semibold flex items-center gap-1.5">
            <Activity className="h-4 w-4" />
            Sorgenti dati
            <span className="text-[11px] font-normal text-muted-foreground ml-1 tabular-nums">
              {healthy}/{totalSources} healthy
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
        {failing > 0 && (
          <div className="text-xs text-red-700 mt-1">
            ⚠ {failing} fonte{failing === 1 ? "" : "i"} in errore — verifica fallback
          </div>
        )}
      </CardHeader>
      <CardContent className="p-0 max-h-[480px] overflow-auto">
        {(["primary", "fallback", "scheduled"] as const).map((role) =>
          groups[role].length > 0 ? (
            <div key={role}>
              <div className="px-4 py-1.5 bg-muted/40 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground border-b">
                {ROLE_LABEL[role]}
              </div>
              {groups[role].map((m) => (
                <SourceRow key={`${m.source}.${m.op}`} m={m} />
              ))}
            </div>
          ) : null
        )}
      </CardContent>
    </Card>
  );
}
