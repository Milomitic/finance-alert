import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Clock, CheckCircle2, XCircle, AlertTriangle, Circle } from "lucide-react";
import type { SchedulerJobStat } from "@/api/platformHealth";

type Props = { jobs: SchedulerJobStat[] };

const RESULT_BADGE: Record<string, { Icon: React.ComponentType<{ className?: string }>; classes: string }> = {
  ok: { Icon: CheckCircle2, classes: "text-emerald-600" },
  error: { Icon: XCircle, classes: "text-red-600" },
  missed: { Icon: AlertTriangle, classes: "text-amber-600" },
};

// Known job → human-readable description (so the card isn't all snake_case)
const JOB_LABEL: Record<string, string> = {
  scan_alerts: "Scan giornaliero alert",
  send_digest: "Digest Telegram",
  refresh_catalog: "Refresh catalogo Wikipedia",
  refresh_fred: "FRED macro series",
  refresh_imminent_earnings: "Earnings imminenti (Finnhub)",
  refresh_institutionals: "Portfolio istituzionali",
  refresh_sec_13f: "SEC 13F filings",
  dedupe_stocks: "Dedupe ticker duplicati",
  cleanup_orphan_scans: "Cleanup scan orfani",
};

function ago(ts: number | null): string {
  if (ts == null) return "—";
  const s = Math.floor(Date.now() / 1000 - ts);
  if (s < 60) return `${s}s fa`;
  if (s < 3600) return `${Math.floor(s / 60)}m fa`;
  if (s < 86400) return `${Math.floor(s / 3600)}h fa`;
  return `${Math.floor(s / 86400)}g fa`;
}

export default function SchedulerCard({ jobs }: Props) {
  const errors = jobs.filter((j) => j.last_result === "error").length;
  const totalRuns = jobs.reduce((acc, j) => acc + j.runs, 0);
  const totalErrors = jobs.reduce((acc, j) => acc + j.errors, 0);

  return (
    <Card className="h-full overflow-hidden">
      <CardHeader className="pb-3 border-b bg-muted/20">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-1.5">
            <Clock className="h-4 w-4" />
            Scheduler
            <span className="text-[10px] font-normal text-muted-foreground ml-1">
              {jobs.length} job tracciati
            </span>
          </CardTitle>
          <span className="text-[10px] text-muted-foreground tabular-nums">
            {totalRuns} runs · {totalErrors} err
          </span>
        </div>
        {errors > 0 && (
          <div className="text-[11px] text-red-700 mt-1">
            ⚠ {errors} job in errore — verifica scheduler
          </div>
        )}
      </CardHeader>
      <CardContent className="p-0 text-xs max-h-[480px] overflow-auto">
        {jobs.length === 0 && (
          <div className="p-4 text-muted-foreground italic text-center">
            <Circle className="h-4 w-4 mx-auto mb-2 opacity-50" />
            Nessun evento registrato dal restart.
            <br />I job appariranno mano a mano che vengono eseguiti.
          </div>
        )}
        {jobs.map((j) => {
          const badge = RESULT_BADGE[j.last_result ?? ""] ?? {
            Icon: Circle,
            classes: "text-muted-foreground",
          };
          const label = JOB_LABEL[j.job_id] ?? j.job_id;
          return (
            <div
              key={j.job_id}
              className="flex items-start gap-2 py-2 px-3 border-b last:border-b-0 hover:bg-muted/30 transition-colors"
            >
              <badge.Icon className={`h-3.5 w-3.5 mt-0.5 shrink-0 ${badge.classes}`} />
              <div className="min-w-0 flex-1">
                <div className="font-medium text-[12.5px] truncate" title={j.job_id}>
                  {label}
                </div>
                <div className="text-[10.5px] text-muted-foreground font-mono truncate">
                  {j.job_id} · {ago(j.last_run_at)}
                </div>
                {j.last_error && (
                  <div className="text-[10px] text-red-700/80 mt-0.5 truncate" title={j.last_error}>
                    ✗ {j.last_error}
                  </div>
                )}
              </div>
              <div className="text-right text-[10px] text-muted-foreground tabular-nums shrink-0">
                <div className="text-emerald-700 font-medium">{j.runs}</div>
                {j.errors > 0 && <div className="text-red-700">{j.errors} err</div>}
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
