import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchHealth, fetchLogs } from "@/api/platformHealth";
import DataSourcesCard from "@/components/health/DataSourcesCard";
import SchedulerCard from "@/components/health/SchedulerCard";
import ScansCard from "@/components/health/ScansCard";
import CacheCard from "@/components/health/CacheCard";
import LogStream from "@/components/health/LogStream";
import { usePlatformHealthStream } from "@/hooks/usePlatformHealthStream";

export default function PlatformHealthPage() {
  const { data: initialLogs } = useQuery({
    queryKey: ["platform-logs-initial"],
    queryFn: () => fetchLogs({ limit: 500 }),
  });
  const { data: initialHealth, isLoading: healthLoading } = useQuery({
    queryKey: ["platform-health"],
    queryFn: fetchHealth,
  });

  const { snapshot, logs, setLogs, connected } = usePlatformHealthStream(
    initialLogs ?? []
  );

  // Prefer the live snapshot from SSE; fall back to the REST snapshot
  // until the first SSE event arrives.
  const health = snapshot ?? initialHealth ?? null;
  const [paused, setPaused] = useState(false);

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Salute piattaforma</h1>
          <p className="text-sm text-muted-foreground">
            Monitoraggio servizi e log in tempo reale.
          </p>
        </div>
        <div className="text-xs">
          {connected ? (
            <span className="text-emerald-700">● Live</span>
          ) : (
            <span className="text-amber-700">● Riconnessione…</span>
          )}
        </div>
      </header>

      {healthLoading && !health && <div>Caricamento…</div>}
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

      <LogStream
        records={logs}
        paused={paused}
        onTogglePause={() => setPaused((p) => !p)}
        onClear={() => setLogs([])}
      />
    </div>
  );
}
