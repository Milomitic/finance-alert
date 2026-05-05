import { AlertTriangle, CheckCircle2, Database, Lightbulb, XCircle } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { cn } from "@/lib/utils";

interface SourceMetric {
  source: string;
  op: string;
  success: number;
  failure: number;
  success_rate: number;       // -1 if no calls yet
  last_success_at: number | null;
  last_failure_at: number | null;
  last_failure_reason: string | null;
  health: "healthy" | "degraded" | "failing" | "idle";
}

interface BreakerStatus {
  state: "closed" | "open" | "half_open";
  failures_in_window?: number;
  seconds_until_probe?: number;
}

interface Suggestion {
  op: string;
  why: string;
  suggestion: string;
}

interface HealthResponse {
  yfinance_breaker: BreakerStatus;
  metrics: SourceMetric[];
  suggestions: Suggestion[];
}

function relTime(epoch: number | null): string {
  if (epoch == null) return "—";
  const diff = Math.abs(Date.now() / 1000 - epoch);
  if (diff < 60) return `${Math.round(diff)}s fa`;
  if (diff < 3600) return `${Math.round(diff / 60)}m fa`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h fa`;
  return `${Math.round(diff / 86400)}g fa`;
}

const HEALTH_COLOR: Record<SourceMetric["health"], string> = {
  healthy: "text-green-600 dark:text-green-400 border-green-500/40 bg-green-50 dark:bg-green-950/20",
  degraded: "text-amber-600 dark:text-amber-400 border-amber-500/40 bg-amber-50 dark:bg-amber-950/20",
  failing: "text-red-600 dark:text-red-400 border-red-500/40 bg-red-50 dark:bg-red-950/20",
  idle: "text-muted-foreground border-border/50",
};

const HEALTH_ICON: Record<SourceMetric["health"], typeof CheckCircle2> = {
  healthy: CheckCircle2,
  degraded: AlertTriangle,
  failing: XCircle,
  idle: Database,
};

function MetricRow({ m }: { m: SourceMetric }) {
  const Icon = HEALTH_ICON[m.health];
  const total = m.success + m.failure;
  return (
    <div className={cn("flex items-center gap-2 px-3 py-2 rounded-md border text-sm", HEALTH_COLOR[m.health])}>
      <Icon className="h-4 w-4 shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-1.5 flex-wrap">
          <span className="font-mono font-bold">{m.source}.{m.op}</span>
          <span className="text-xs opacity-80 capitalize">{m.health}</span>
        </div>
        <div className="text-[11px] opacity-80 tabular-nums">
          {total > 0 ? (
            <>
              {(m.success_rate * 100).toFixed(0)}% success ·
              {" "}{m.success.toLocaleString()} ok / {m.failure.toLocaleString()} fail
            </>
          ) : "no calls yet"}
        </div>
        {m.last_success_at != null && (
          <div className="text-[10px] opacity-70 tabular-nums">
            ✓ ultimo {relTime(m.last_success_at)}
            {m.last_failure_at != null && <> · ✗ ultimo {relTime(m.last_failure_at)}</>}
          </div>
        )}
        {m.last_failure_reason && m.health !== "healthy" && (
          <div className="text-[10px] opacity-80 truncate" title={m.last_failure_reason}>
            ↳ {m.last_failure_reason}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Data sources health card. Surfaces per-source per-op success rates plus
 * actionable suggestions when an operation has no working source. Polls every
 * 60s — staleness is fine since these counters move slowly.
 */
export function DataSourcesCard() {
  const q = useQuery({
    queryKey: ["health", "data-sources"],
    queryFn: () => api<HealthResponse>("/api/health/data-sources"),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  if (q.isLoading) {
    return (
      <Card>
        <CardContent className="p-4">
          <SectionTitle icon={Database} label="Data Sources" className="mb-2" />
          <div className="h-24 animate-pulse bg-muted/40 rounded" />
        </CardContent>
      </Card>
    );
  }

  const data = q.data;
  if (!data) return null;

  const breakerColor =
    data.yfinance_breaker.state === "open"
      ? "text-red-700 dark:text-red-300 bg-red-100 dark:bg-red-900/30"
      : data.yfinance_breaker.state === "half_open"
        ? "text-amber-700 dark:text-amber-300 bg-amber-100 dark:bg-amber-900/30"
        : "text-green-700 dark:text-green-300 bg-green-100 dark:bg-green-900/30";

  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={Database}
          label="Data sources"
          right={
            <span className={cn("text-[11px] px-2 py-0.5 rounded font-semibold", breakerColor)}>
              yfinance breaker: {data.yfinance_breaker.state}
              {data.yfinance_breaker.state === "open" && data.yfinance_breaker.seconds_until_probe != null && (
                <> · probe tra {Math.round(data.yfinance_breaker.seconds_until_probe)}s</>
              )}
            </span>
          }
          className="mb-3 pb-2 border-b border-border/50"
        />

        {data.metrics.length === 0 ? (
          <div className="text-xs text-muted-foreground">
            Nessuna chiamata registrata ancora. Le metriche si popolano dopo il primo scan / refresh fundamentals.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
            {data.metrics.map((m) => <MetricRow key={`${m.source}.${m.op}`} m={m} />)}
          </div>
        )}

        {data.suggestions.length > 0 && (
          <div className="mt-3 px-3 py-2 rounded-md bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/40">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-700 dark:text-amber-300 mb-1">
              <Lightbulb className="h-3.5 w-3.5" /> Suggerimenti per integrare nuove fonti
            </div>
            <ul className="space-y-1 text-xs text-amber-900 dark:text-amber-100">
              {data.suggestions.map((s, i) => (
                <li key={i}>
                  <span className="font-mono font-semibold">{s.op}</span>: {s.why}
                  <div className="text-[11px] opacity-80 italic">→ {s.suggestion}</div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
