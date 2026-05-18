import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, AlertTriangle, XCircle, Wifi, WifiOff, RefreshCw } from "lucide-react";
import { fetchHealth, fetchLogs, runProbesNow } from "@/api/platformHealth";
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
    desc: "Una sorgente fallback/scheduled o un job è fuori servizio, ma le sorgenti primarie funzionano — nessun impatto bloccante.",
    Icon: AlertTriangle,
    bg: "bg-amber-50",
    fg: "text-amber-700",
    border: "border-amber-200",
  },
  outage: {
    label: "Outage in corso",
    desc: "Una sorgente dati PRIMARIA è in errore critico (o il breaker yfinance è aperto / uno scan è bloccato) — verifica subito.",
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

  // Manual refresh: triggers all probes server-side and invalidates the
  // local query cache so the next /health snapshot reflects the run.
  const queryClient = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);
  const [refreshedAt, setRefreshedAt] = useState<number | null>(null);
  const triggerRefresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    try {
      await runProbesNow();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["platform-health"] }),
        queryClient.invalidateQueries({ queryKey: ["platform-logs-initial"] }),
      ]);
      setRefreshedAt(Date.now());
    } catch (err) {
      // Surface in console; the operator will still see the status
      // refresh via SSE on the normal 5s cadence.
      console.error("[platform-health] manual refresh failed:", err);
    } finally {
      setRefreshing(false);
    }
  };

  // Derive overall status from the health snapshot for the hero banner
  const overall: OverallStatus = useMemo(() => {
    if (!health) return "operational";
    const breakerOpen =
      String(health.yfinance_breaker.state ?? "closed").toLowerCase() !== "closed";
    // Outage is reserved for PRIMARY data-path failures. A failing
    // fallback (e.g. Marketaux without an API key) or a failing
    // scheduled source means reduced resilience, NOT a user-visible
    // outage — the app still serves data off the primary sources. So
    // only `role === "primary"` failures escalate to red.
    const failingPrimary = health.data_sources.filter(
      (m) => m.role === "primary" && m.health === "failing"
    ).length;
    const failingNonPrimary = health.data_sources.filter(
      (m) => m.role !== "primary" && m.health === "failing"
    ).length;
    const erroredJobs = health.scheduler.filter(
      (j) => j.last_result === "error"
    ).length;
    const runningScanStuck = health.scans.some((s) => {
      if (s.status !== "running" || !s.started_at) return false;
      const elapsedMs = Date.now() - new Date(s.started_at).getTime();
      // Guardrail: if the diff is negative (clock skew) or implausibly
      // large (>24h, almost certainly a timezone parsing issue), don't
      // claim outage on this signal. The 30-min threshold is for genuine
      // stuck scans where the worker died silently.
      if (elapsedMs < 0 || elapsedMs > 24 * 3600_000) return false;
      return elapsedMs > 30 * 60_000;
    });
    if (breakerOpen || failingPrimary > 0 || runningScanStuck) return "outage";
    const degraded =
      // Any primary source merely degraded (not failing) …
      health.data_sources.some(
        (m) => m.role === "primary" && m.health === "degraded"
      ) ||
      // … OR any fallback/scheduled source failing or degraded …
      failingNonPrimary > 0 ||
      health.data_sources.some(
        (m) => m.role !== "primary" && m.health === "degraded"
      ) ||
      // … OR an errored scheduler job.
      erroredJobs > 0;
    if (degraded) return "degraded";
    return "operational";
  }, [health]);

  const status = STATUS_INFO[overall];

  return (
    <div className="mx-auto w-full max-w-[1800px] space-y-8 pb-12">
      {/* Header — title + global status pill, à la Claude status */}
      <header className="space-y-3">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="space-y-1.5">
            <h1 className="text-4xl font-bold tracking-tight">Salute piattaforma</h1>
            <p className="text-base text-muted-foreground">
              Stato live di sorgenti dati, scheduler, scan e log — aggiornato in tempo reale via SSE.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={triggerRefresh}
              disabled={refreshing}
              className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full border text-sm font-medium transition-colors ${
                refreshing
                  ? "bg-sky-50 text-sky-700 border-sky-200 cursor-wait"
                  : "bg-background text-foreground border-border hover:bg-muted"
              }`}
              title={
                refreshing
                  ? "Esecuzione probe in corso (~5-10s)…"
                  : refreshedAt
                    ? `Ultimo refresh manuale: ${new Date(refreshedAt).toLocaleTimeString()}`
                    : "Forza un refresh sincrono di tutte le sorgenti dati"
              }
              aria-label="Aggiorna stato sorgenti dati"
            >
              <RefreshCw
                className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`}
              />
              {refreshing ? "Aggiornando…" : "Aggiorna"}
            </button>
            <div
              className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full border text-sm font-medium ${
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
                  <Wifi className="h-3.5 w-3.5" /> Live
                </>
              ) : (
                <>
                  <WifiOff className="h-3.5 w-3.5" /> Riconnessione…
                </>
              )}
            </div>
          </div>
        </div>

        {/* Overall status banner */}
        <div
          className={`flex items-start gap-3 rounded-lg border p-5 ${status.bg} ${status.border}`}
        >
          <status.Icon className={`h-7 w-7 mt-0.5 shrink-0 ${status.fg}`} />
          <div className="min-w-0 flex-1">
            <div className={`text-lg font-semibold ${status.fg}`}>
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
