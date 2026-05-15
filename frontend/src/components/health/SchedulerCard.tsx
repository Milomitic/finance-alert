import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import type { SchedulerJobStat } from "@/api/platformHealth";

type Props = { jobs: SchedulerJobStat[] };

const RESULT_TONE: Record<string, string> = {
  ok: "text-emerald-700",
  error: "text-red-700",
  missed: "text-amber-700",
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
  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="text-sm">
          Scheduler{" "}
          <span className="text-xs text-muted-foreground">
            ({jobs.length} job{errors > 0 && `, ${errors} in errore`})
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="text-xs space-y-1">
        {jobs.length === 0 && (
          <div className="text-muted-foreground italic">
            Nessun evento registrato ancora
          </div>
        )}
        {jobs.map((j) => (
          <div
            key={j.job_id}
            className="flex items-center justify-between gap-2"
          >
            <span className="font-mono truncate" title={j.job_id}>
              {j.job_id}
            </span>
            <span
              className={
                RESULT_TONE[j.last_result ?? ""] ?? "text-muted-foreground"
              }
            >
              {j.last_result ?? "—"} · {ago(j.last_run_at)}
            </span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
