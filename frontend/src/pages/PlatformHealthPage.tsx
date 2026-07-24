import { useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, AlertTriangle, XCircle, Wifi, WifiOff, RefreshCw } from "lucide-react";
import {
  fetchHealth,
  fetchLogs,
  fetchProbeProgress,
  runProbesNow,
} from "@/api/platformHealth";
import { QueryError } from "@/components/ui/query-error";
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
    bg: "bg-emerald-50 dark:bg-emerald-950/40",
    fg: "text-emerald-700 dark:text-emerald-300",
    border: "border-emerald-200 dark:border-emerald-800/60",
  },
  degraded: {
    label: "Servizi degradati",
    desc: "Una sorgente fallback/scheduled o un job è fuori servizio, ma le sorgenti primarie funzionano — nessun impatto bloccante.",
    Icon: AlertTriangle,
    bg: "bg-amber-50 dark:bg-amber-950/40",
    fg: "text-amber-700 dark:text-amber-300",
    border: "border-amber-200 dark:border-amber-800/60",
  },
  outage: {
    label: "Outage in corso",
    desc: "Una sorgente dati PRIMARIA è in errore critico (o il breaker yfinance è aperto / uno scan è bloccato) — verifica subito.",
    Icon: XCircle,
    bg: "bg-red-50 dark:bg-red-950/40",
    fg: "text-red-700 dark:text-red-300",
    border: "border-red-200 dark:border-red-800/60",
  },
};

export default function PlatformHealthPage() {
  const { data: initialLogs } = useQuery({
    queryKey: ["platform-logs-initial"],
    queryFn: () => fetchLogs({ limit: 500 }),
  });
  const {
    data: initialHealth,
    isLoading: healthLoading,
    isError: healthError,
    isFetching: healthFetching,
    refetch: refetchHealth,
  } = useQuery({
    queryKey: ["platform-health"],
    queryFn: fetchHealth,
  });

  const { snapshot, logs, setLogs, connected } = usePlatformHealthStream(
    initialLogs ?? []
  );

  // Prefer the live snapshot from SSE; fall back to REST until first event.
  const health = snapshot ?? initialHealth ?? null;
  const [paused, setPaused] = useState(false);

  // Clicking a data source in the "Fonti dati" card filters the live-log
  // table to that source and scrolls it into view, so its errors (e.g. a
  // Finnhub HTTP 403) are immediately visible.
  const [sourceFilter, setSourceFilter] = useState<
    { label: string; tokens: string[] } | null
  >(null);
  const logStreamRef = useRef<HTMLDivElement>(null);
  const selectSource = (label: string, tokens: string[]) => {
    setSourceFilter({ label, tokens });
    logStreamRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  // Manual refresh: triggers all probes server-side and invalidates the
  // local query cache so the next /health snapshot reflects the run.
  const queryClient = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);
  const [progressPct, setProgressPct] = useState(0);
  const [refreshedAt, setRefreshedAt] = useState<number | null>(null);
  // Same spinner+% contract as the pre-market card: kick the run
  // (202), then poll {refreshing, progress_pct} so the bar tracks the
  // real per-probe progress instead of a blind ~5-10s block.
  const triggerRefresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    setProgressPct(0);
    try {
      await runProbesNow();
      // Poll until the backend reports the run finished (or a safety
      // cap so a wedged run can't spin forever).
      const deadline = Date.now() + 60_000;
      // small initial delay so the first poll sees refreshing=true
      for (;;) {
        await new Promise((r) => setTimeout(r, 700));
        let p: { refreshing: boolean; progress_pct: number };
        try {
          p = await fetchProbeProgress();
        } catch {
          break; // progress endpoint hiccup → stop polling, refetch
        }
        setProgressPct(p.progress_pct);
        if (!p.refreshing || Date.now() > deadline) break;
      }
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
      setProgressPct(0);
    }
  };

  // Overall status for the hero banner: the SERVER rollup is the single
  // truth (health_rollup.compute_rollup — same rules everywhere, feeds the
  // Telegram transition push too). The client derivation below survives
  // ONLY as fallback for pre-rollup payloads.
  const overall: OverallStatus = useMemo(() => {
    if (!health) return "operational";
    if (
      health.overall === "operational" ||
      health.overall === "degraded" ||
      health.overall === "outage"
    ) {
      return health.overall;
    }
    // ── Fallback client derivation (old payloads without `overall`) ──
    const breakerOpen =
      String(health.yfinance_breaker.state ?? "closed").toLowerCase() !== "closed";
    // Outage is reserved for PRIMARY data-path failures. A failing
    // fallback (e.g. Marketaux without an API key) or a failing
    // scheduled source means reduced resilience, NOT a user-visible
    // outage. Sources in "unavailable" (plan-gated 403) are excluded
    // from BOTH tiers — a tier limitation is not an incident.
    const failingPrimary = health.data_sources.filter(
      (m) => m.role === "primary" && m.health === "failing"
    ).length;
    const failingNonPrimary = health.data_sources.filter(
      (m) => m.role !== "primary" && m.health === "failing"
    ).length;
    // error OR missed: a missed tick means the scheduler is falling behind —
    // the silent-death mode the 13F crons hit for months.
    const erroredJobs = health.scheduler.filter(
      (j) => j.last_result === "error" || j.last_result === "missed"
    ).length;
    const runningScanStuck = health.scans.some((s) => {
      if (s.status !== "running" || !s.started_at) return false;
      const elapsedMs = Date.now() - new Date(s.started_at).getTime();
      // Only negative diffs (clock skew) are excluded. The old >24h
      // guard is GONE: it masked a genuinely multi-day-stuck scan.
      if (elapsedMs < 0) return false;
      return elapsedMs > 30 * 60_000;
    });
    if (breakerOpen || failingPrimary > 0 || runningScanStuck) return "outage";
    // Last scan crashed (user-cancelled runs carry the "Cancellato" sentinel).
    const lastScan = health.scans[0];
    const lastScanFailed =
      !!lastScan &&
      lastScan.status === "failed" &&
      !(lastScan.error_message ?? "").startsWith("Cancellato");
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
      // … OR an errored/missed scheduler job OR a crashed last scan.
      erroredJobs > 0 ||
      lastScanFailed;
    if (degraded) return "degraded";
    return "operational";
  }, [health]);

  const status = STATUS_INFO[overall];
  const reasons = health?.reasons ?? [];

  return (
    <div className="mx-auto w-full max-w-[1800px] space-y-8 pb-12">
      {/* Header — title + global status pill, à la Claude status */}
      <header className="space-y-3">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="space-y-1.5">
            <h1 className="text-2xl sm:text-4xl font-bold tracking-tight">Salute piattaforma</h1>
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
                  ? "bg-sky-50 dark:bg-sky-950/40 text-sky-700 dark:text-sky-300 border-sky-200 dark:border-sky-800/60 cursor-wait"
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
              {refreshing
                ? `Aggiornando… ${progressPct}%`
                : "Aggiorna"}
            </button>
            <div
              className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full border text-sm font-medium ${
                connected
                  ? "bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800/60"
                  : "bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800/60"
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

        {/* Overall status banner — only when we actually have a snapshot.
            Without this guard a failed initial fetch (health null) showed a
            falsely-green "operational" banner over an empty body. */}
        {health && (
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
            {/* Motivi puntuali dal rollup server-side — il "perché" del
                banner senza dover scavare nelle card sottostanti. */}
            {overall !== "operational" && reasons.length > 0 && (
              <ul className="mt-2 space-y-0.5 text-sm text-muted-foreground list-disc list-inside">
                {reasons.map((r) => (
                  <li key={r} className="truncate" title={r}>
                    {r}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
        )}
      </header>

      {/* Loading state */}
      {healthLoading && !health && (
        <div className="rounded-lg border bg-card p-8 text-center text-muted-foreground">
          Caricamento snapshot iniziale…
        </div>
      )}

      {/* Hard-failure state: initial fetch errored and SSE hasn't delivered a
          snapshot — surface a retry instead of the empty (falsely-green) body. */}
      {!health && !healthLoading && (
        <div className="rounded-lg border bg-card p-8">
          <QueryError
            message="dello stato piattaforma"
            onRetry={refetchHealth}
            isRetrying={healthFetching}
          />
          {!healthError && (
            <p className="mt-2 text-xs text-muted-foreground">
              In attesa del primo evento SSE…
            </p>
          )}
        </div>
      )}

      {/* Fonti dati — the clustered overview, full-width on top. */}
      {health && (
        <DataSourcesCard
          metrics={health.data_sources}
          yfinanceBreaker={health.yfinance_breaker}
          suggestions={health.suggestions ?? []}
          onSelectSource={selectSource}
        />
      )}

      {/* Secondary operational cards. */}
      {health && (
        <div className="grid gap-4 lg:grid-cols-3 [&>*]:min-w-0">
          <SchedulerCard jobs={health.scheduler} />
          <ScansCard scans={health.scans} />
          <CacheCard cache={health.cache} />
        </div>
      )}

      <div ref={logStreamRef} className="scroll-mt-4">
        <LogStream
          records={logs}
          paused={paused}
          onTogglePause={() => setPaused((p) => !p)}
          onClear={() => setLogs([])}
          sourceFilter={sourceFilter}
          onClearSourceFilter={() => setSourceFilter(null)}
        />
      </div>
    </div>
  );
}
