import { useQuery } from "@tanstack/react-query";
import { fetchHealth, fetchLogs } from "@/api/platformHealth";
import DataSourcesCard from "@/components/health/DataSourcesCard";
import SchedulerCard from "@/components/health/SchedulerCard";
import ScansCard from "@/components/health/ScansCard";
import CacheCard from "@/components/health/CacheCard";

export default function PlatformHealthPage() {
  const { data: health, isLoading: healthLoading } = useQuery({
    queryKey: ["platform-health"],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
  });

  const { data: initialLogs } = useQuery({
    queryKey: ["platform-logs-initial"],
    queryFn: () => fetchLogs({ limit: 500 }),
  });

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Salute piattaforma</h1>
        <p className="text-sm text-muted-foreground">
          Monitoraggio servizi e log in tempo reale.
        </p>
      </header>

      {healthLoading && <div>Caricamento…</div>}
      {health && (
        <div className="grid gap-3 lg:grid-cols-4">
          <DataSourcesCard
            metrics={health.data_sources}
            yfinanceBreaker={health.yfinance_breaker}
          />
          <SchedulerCard jobs={health.scheduler} />
          <ScansCard scans={health.scans} />
          <CacheCard cache={health.cache} />
        </div>
      )}

      <section className="space-y-2">
        <h2 className="text-lg font-semibold">Log</h2>
        <div className="rounded border bg-background p-2 max-h-[400px] overflow-auto font-mono text-xs space-y-1">
          {(initialLogs ?? []).slice(-200).map((r, i) => (
            <div key={i} className="flex gap-2">
              <span className="text-muted-foreground">
                {new Date(r.ts * 1000).toLocaleTimeString()}
              </span>
              <span className="font-semibold w-16">{r.level}</span>
              <span className="text-muted-foreground">[{r.module}]</span>
              <span className="flex-1 truncate">{r.message}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
