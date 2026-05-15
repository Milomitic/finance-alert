import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, AlertTriangle, XCircle, Wifi, WifiOff } from "lucide-react";
import { fetchHealth, fetchLogs } from "@/api/platformHealth";
import DataSourcesCard from "@/components/health/DataSourcesCard";
import SchedulerCard from "@/components/health/SchedulerCard";
import ScansCard from "@/components/health/ScansCard";
import CacheCard from "@/components/health/CacheCard";
import LogStream from "@/components/health/LogStream";
import { usePlatformHealthStream } from "@/hooks/usePlatformHealthStream";

type OverallStatus = "operational" | "degraded" | "outage";

const STATUS_INFO: Record<
  OverallStatus,
  {
    label: string;
    desc: string;
    Icon: React.ComponentType<{ className?: string }>;
    bg: string;
    fg: string;
    border: string;
  }
> = {
  operational: {
    label: "Tutti i sistemi operativi",
    desc: "Nessuna anomalia rilevata negli ultimi minuti.",
    Icon: CheckCircle2,
    bg: "bg-emerald-50",
    fg: "text-emerald-700",
    border: "border-emerald-200",
  },
  degraded: {
    label: "Servizi degradati",
    desc: "Una o più sorgenti dati riportano errori non bloccanti.",
    Icon: AlertTriangle,
    bg: "bg-amber-50",
    fg: "text-amber-700",
    border: "border-amber-200",
  },
  outage: {
    label: "Outage in corso",
    desc: "Almeno una sorgente o un job è in errore critico — verifica subito.",
    Icon: XCircle,
    bg: "bg-red-50",
    fg: "text-red-700",
    border: "border-red-200",
  },
};

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

  // Prefer the live snapshot from SSE; fall back to REST until first event.
  const health = snapshot ?? initialHealth ?? null;
  const [paused, setPaused] = useState(false);

  // Derive overall status from the health snapshot for the hero banner
  const overall: OverallStatus = useMemo(() => {
    if (!health) return "operational";
    const breakerOpen =
      String(health.yfinance_breaker.state ?? "closed").toLowerCase() !== "closed";
    const failingSources = health.data_sources.filter(
      (m) => m.health === "failing"
    ).length;
    const erroredJobs = health.scheduler.filter(
      (j) => j.last_result === "error"
    ).length;
    const runningScanStuck = health.scans.some(
      (s) =>
        s.status === "running" &&
        s.started_at &&
        Date.now() - new Date(s.started_at).getTime() > 30 * 60_000
    );
    if (breakerOpen || failingSources > 0 || runningScanStuck) return "outage";
    const degraded =
      health.data_sources.filter((m) => m.health === "degraded").length > 0 ||
      erroredJobs > 0;
    if (degraded) return "degraded";
    return "operational";
  }, [health]);

  const status = STATUS_INFO[overall];

  return (
    <div className="mx-auto max-w-7xl space-y-8 pb-12">
      {/* Header — title + global status pill, à la Claude status */}
      <header className="space-y-3">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="space-y-1">
            <h1 className="text-3xl font-bold tracking-tight">Salute piattaforma</h1>
            <p className="text-sm text-muted-foreground">
              Stato live di sorgenti dati, scheduler, scan e log — aggiornato in tempo reale via SSE.
            </p>
          </div>
          <div
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs font-medium ${
              connected
                ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                : "bg-amber-50 text-amber-700 border-amber-200"
            }`}
            title={
              connected
                ? "Connessione SSE attiva — eventi push in tempo reale"
                : "Riconnessione SSE in corso — i dati potrebbero essere fermi"
            }
          >
            {connected ? (
              <>
                <Wifi className="h-3 w-3" /> Live
              </>
            ) : (
              <>
                <WifiOff className="h-3 w-3" /> Riconnessione…
              </>
            )}
          </div>
        </div>

        {/* Overall status banner */}
        <div
          className={`flex items-start gap-3 rounded-lg border p-4 ${status.bg} ${status.border}`}
        >
          <status.Icon className={`h-6 w-6 mt-0.5 shrink-0 ${status.fg}`} />
          <div className="min-w-0 flex-1">
            <div className={`text-base font-semibold ${status.fg}`}>
              {status.label}
            </div>
            <p className="text-sm text-muted-foreground mt-0.5">
              {status.desc}
            </p>
          </div>
        </div>
      </header>

      {/* Loading state */}
      {healthLoading && !health && (
        <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
          Caricamento snapshot iniziale…
        </div>
      )}

      {/* Cards grid */}
      {health && (
        <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-4">
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
