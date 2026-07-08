import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Clock, CheckCircle2, XCircle, AlertTriangle, Circle, CalendarClock } from "lucide-react";
import type { SchedulerJobStat } from "@/api/platformHealth";

type Props = { jobs: SchedulerJobStat[] };

const RESULT_BADGE: Record<string, { Icon: React.ComponentType<{ className?: string }>; classes: string }> = {
  ok: { Icon: CheckCircle2, classes: "text-emerald-600" },
  error: { Icon: XCircle, classes: "text-red-600" },
  missed: { Icon: AlertTriangle, classes: "text-amber-600" },
};

// Known job → human-readable description (so the card isn't all snake_case).
// Every job id registered in backend/app/scheduler/__init__.py must have an
// entry here — a new job without a label renders as raw snake_case (audit
// 2026-07-08 found 8 missing).
const JOB_LABEL: Record<string, string> = {
  scan_alerts: "Scan giornaliero alert",
  scan_alerts_eu_close: "Scan serale post-chiusura EU",
  send_digest: "Digest Telegram",
  refresh_catalog: "Refresh catalogo Wikipedia",
  refresh_fred: "FRED macro series",
  refresh_imminent_earnings: "Earnings imminenti (Finnhub)",
  refresh_institutionals: "Portfolio istituzionali (Dataroma)",
  refresh_sec_13f: "SEC 13F filings",
  refresh_premarket: "Refresh pre-market USA",
  dedupe_stocks: "Dedupe ticker duplicati",
  cleanup_orphan_scans: "Cleanup scan orfani",
  db_backup: "Backup notturno DB",
  retention: "Retention scan_runs",
  live_movers_sweep: "Sweep live top movers",
  kpi_rollup: "Rollup KPI giornaliero",
  health_probes_fast: "Probe salute (set veloce)",
  health_probes_slow: "Probe salute (set lento)",
};

// Grace window before a past-due next_run_time reads as "in ritardo": the
// scheduler tick + a long-running previous job can legitimately postpone a
// fire by a few minutes, so alarm only when the miss is unambiguous.
const LATE_GRACE_MS = 15 * 60_000;

function ago(ts: number | null): string {
  if (ts == null) return "—";
  const s = Math.floor(Date.now() / 1000 - ts);
  if (s < 60) return `${s}s fa`;
  if (s < 3600) return `${Math.floor(s / 60)}m fa`;
  if (s < 86400) return `${Math.floor(s / 3600)}h fa`;
  return `${Math.floor(s / 86400)}g fa`;
}

/** "tra 12m" / "tra 3h 05m" / "sab 04:00" for the next scheduled fire. */
function nextRunLabel(ts: number): string {
  const deltaS = Math.floor(ts - Date.now() / 1000);
  if (deltaS <= 0) return "ora";
  if (deltaS < 60) return `tra ${deltaS}s`;
  if (deltaS < 3600) return `tra ${Math.floor(deltaS / 60)}m`;
  if (deltaS < 86400) {
    const h = Math.floor(deltaS / 3600);
    const m = Math.floor((deltaS % 3600) / 60);
    return `tra ${h}h ${String(m).padStart(2, "0")}m`;
  }
  return new Date(ts * 1000).toLocaleString("it-IT", {
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** A registered job whose next_run_time is in the past beyond the grace
 *  window: the scheduler should have fired it and didn't (dead scheduler
 *  thread, wedged previous run) — the exact silent-death mode the 13F
 *  crons hit for months. */
function isLate(j: SchedulerJobStat): boolean {
  if (j.next_run_time == null) return false;
  return Date.now() > j.next_run_time * 1000 + LATE_GRACE_MS;
}

export default function SchedulerCard({ jobs }: Props) {
  const errors = jobs.filter((j) => j.last_result === "error").length;
  const lateJobs = jobs.filter(isLate).length;
  const totalRuns = jobs.reduce((acc, j) => acc + j.runs, 0);
  const totalErrors = jobs.reduce((acc, j) => acc + j.errors, 0);

  return (
    <Card className="h-full overflow-hidden">
      <CardHeader className="pb-3 border-b bg-muted/20">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base font-semibold flex items-center gap-1.5">
            <Clock className="h-4 w-4" />
            Scheduler
            <span className="text-[11px] font-normal text-muted-foreground ml-1">
              {jobs.length} job registrati
            </span>
          </CardTitle>
          <span className="text-[11px] text-muted-foreground tabular-nums">
            {totalRuns} runs · {totalErrors} err
          </span>
        </div>
        {errors > 0 && (
          <div className="text-xs text-red-700 dark:text-red-400 mt-1">
            ⚠ {errors} job in errore — verifica scheduler
          </div>
        )}
        {lateJobs > 0 && (
          <div className="text-xs text-amber-700 dark:text-amber-400 mt-1">
            ⚠ {lateJobs} job in ritardo sulla schedulazione — possibile scheduler bloccato
          </div>
        )}
      </CardHeader>
      <CardContent className="p-0 text-sm max-h-[480px] overflow-auto">
        {jobs.length === 0 && (
          <div className="p-4 text-muted-foreground italic text-center text-sm">
            <Circle className="h-4 w-4 mx-auto mb-2 opacity-50" />
            Nessun job registrato.
            <br />Lo scheduler potrebbe non essere partito.
          </div>
        )}
        {jobs.map((j) => {
          const badge = RESULT_BADGE[j.last_result ?? ""] ?? {
            Icon: Circle,
            classes: "text-muted-foreground",
          };
          const label = JOB_LABEL[j.job_id] ?? j.job_id;
          const late = isLate(j);
          return (
            <div
              key={j.job_id}
              className="flex items-start gap-2.5 py-2.5 px-4 border-b last:border-b-0 hover:bg-muted/30 transition-colors"
            >
              <badge.Icon className={`h-4 w-4 mt-0.5 shrink-0 ${badge.classes}`} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 min-w-0">
                  <span className="font-medium text-sm truncate" title={j.job_id}>
                    {label}
                  </span>
                  {late && (
                    <span
                      className="shrink-0 inline-flex items-center gap-1 px-1.5 py-0.5 text-[9.5px] font-medium rounded border bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-800/60"
                      title={
                        j.next_run_time != null
                          ? `Doveva partire alle ${new Date(j.next_run_time * 1000).toLocaleString("it-IT")} e non risulta eseguito`
                          : "Job in ritardo sulla schedulazione"
                      }
                    >
                      <AlertTriangle className="h-3 w-3" />
                      in ritardo
                    </span>
                  )}
                </div>
                <div className="text-[11px] text-muted-foreground font-mono truncate mt-0.5" title={j.trigger ?? undefined}>
                  {j.job_id} · {j.last_run_at != null ? ago(j.last_run_at) : "mai eseguito"}
                </div>
                {j.next_run_time != null && !late && (
                  <div className="text-[11px] text-muted-foreground mt-0.5 flex items-center gap-1">
                    <CalendarClock className="h-3 w-3 shrink-0" />
                    prossimo: {nextRunLabel(j.next_run_time)}
                  </div>
                )}
                {j.next_run_time == null && j.trigger == null && (
                  <div className="text-[11px] text-muted-foreground italic mt-0.5">
                    non più registrato (storico)
                  </div>
                )}
                {j.last_error && (
                  <div className="text-[11px] text-red-700/80 dark:text-red-400/80 mt-0.5 truncate" title={j.last_error}>
                    ✗ {j.last_error}
                  </div>
                )}
              </div>
              <div className="text-right text-[11px] text-muted-foreground tabular-nums shrink-0">
                <div className="text-emerald-700 dark:text-emerald-400 font-medium">{j.runs}</div>
                {j.errors > 0 && <div className="text-red-700 dark:text-red-400">{j.errors} err</div>}
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
