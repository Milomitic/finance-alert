import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchHealth, fetchLogs, type LogRecord } from "@/api/platformHealth";
import DataSourcesCard from "@/components/health/DataSourcesCard";
import SchedulerCard from "@/components/health/SchedulerCard";
import ScansCard from "@/components/health/ScansCard";
import CacheCard from "@/components/health/CacheCard";
import LogStream from "@/components/health/LogStream";

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

  const [logs, setLogs] = useState<LogRecord[]>([]);
  const [paused, setPaused] = useState(false);

  // Hydrate the local buffer once when the initial query resolves.
  // (Task 11 will replace this with an EventSource subscription that
  // appends new records as they arrive.)
  useEffect(() => {
    if (initialLogs) setLogs(initialLogs);
  }, [initialLogs]);

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

      <LogStream
        records={logs}
        paused={paused}
        onTogglePause={() => setPaused((p) => !p)}
        onClear={() => setLogs([])}
      />
    </div>
  );
}
