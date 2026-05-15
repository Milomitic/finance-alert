import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Radar, CheckCircle2, XCircle, Loader2, Bell } from "lucide-react";
import type { RecentScan } from "@/api/platformHealth";

type Props = { scans: RecentScan[] };

const STATUS_BADGE: Record<
  string,
  {
    label: string;
    classes: string;
    Icon: React.ComponentType<{ className?: string }>;
  }
> = {
  success: { label: "Success", classes: "bg-emerald-50 text-emerald-700 border-emerald-200", Icon: CheckCircle2 },
  ok: { label: "Success", classes: "bg-emerald-50 text-emerald-700 border-emerald-200", Icon: CheckCircle2 },
  running: { label: "Running", classes: "bg-sky-50 text-sky-700 border-sky-200", Icon: Loader2 },
  failed: { label: "Failed", classes: "bg-red-50 text-red-700 border-red-200", Icon: XCircle },
  error: { label: "Failed", classes: "bg-red-50 text-red-700 border-red-200", Icon: XCircle },
};

function fmtDuration(s: number | null): string {
  if (s == null) return "—";
  if (s < 60) return `${s.toFixed(1)}s`;
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("it-IT", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function ScansCard({ scans }: Props) {
  const last = scans[0];
  const last24h = scans.filter((s) => {
    if (!s.completed_at) return false;
    return Date.now() - new Date(s.completed_at).getTime() < 86400_000;
  });
  const successRate24h =
    last24h.length > 0
      ? (last24h.filter((s) => s.status === "success" || s.status === "ok").length / last24h.length) * 100
      : null;

  return (
    <Card className="h-full overflow-hidden">
      <CardHeader className="pb-3 border-b bg-muted/20">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base font-semibold flex items-center gap-1.5">
            <Radar className="h-4 w-4" />
            Scan recenti
            <span className="text-[11px] font-normal text-muted-foreground ml-1">
              ultimi {scans.length}
            </span>
          </CardTitle>
          {successRate24h !== null && (
            <span className="text-[11px] text-muted-foreground tabular-nums">
              {successRate24h.toFixed(0)}% / 24h
            </span>
          )}
        </div>
      </CardHeader>
      <CardContent className="p-0 text-sm max-h-[480px] overflow-auto">
        {!last && (
          <div className="p-4 text-muted-foreground italic text-center text-sm">
            Nessuno scan ancora.
          </div>
        )}

        {last && (() => {
          const badge = STATUS_BADGE[last.status] ?? STATUS_BADGE.success;
          const progressPct =
            last.progress_total && last.progress_done
              ? (last.progress_done / last.progress_total) * 100
              : null;
          return (
            <div className="p-4 border-b bg-muted/10">
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Ultimo scan
                </span>
                <span
                  className={`inline-flex items-center gap-1 px-2.5 py-0.5 text-[11px] font-medium rounded-full border ${badge.classes}`}
                >
                  <badge.Icon
                    className={`h-3 w-3 ${last.status === "running" ? "animate-spin" : ""}`}
                  />
                  {badge.label}
                </span>
              </div>
              <div className="font-mono text-sm font-medium">
                #{last.id}
                <span className="ml-1.5 text-muted-foreground font-normal">
                  {last.trigger}
                </span>
              </div>
              <div className="text-xs text-muted-foreground mt-1 tabular-nums">
                {fmtDate(last.started_at)} · {fmtDuration(last.duration_s)}
                {last.alerts_count != null && (
                  <>
                    {" · "}
                    <span className="inline-flex items-center gap-0.5">
                      <Bell className="h-3 w-3" />
                      {last.alerts_count}
                    </span>
                  </>
                )}
              </div>
              {progressPct !== null && last.status === "running" && (
                <div className="mt-2">
                  <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                    <span>{last.phase}</span>
                    <span className="tabular-nums">
                      {last.progress_done}/{last.progress_total}
                    </span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-muted overflow-hidden mt-0.5">
                    <div
                      className="h-full bg-sky-500 transition-all"
                      style={{ width: `${progressPct}%` }}
                    />
                  </div>
                </div>
              )}
              {last.error_message && (
                <div
                  className="text-[11px] text-red-700/90 mt-1.5 truncate font-mono"
                  title={last.error_message}
                >
                  ✗ {last.error_message}
                </div>
              )}
            </div>
          );
        })()}

        {scans.slice(1).map((s) => {
          const badge = STATUS_BADGE[s.status] ?? STATUS_BADGE.success;
          return (
            <div
              key={s.id}
              className="flex items-center justify-between gap-2 px-4 py-2 border-b last:border-b-0 hover:bg-muted/30 transition-colors"
            >
              <div className="min-w-0 flex-1">
                <div className="text-[12.5px] font-mono">
                  #{s.id}{" "}
                  <span className="text-muted-foreground">
                    {fmtDate(s.completed_at)} · {fmtDuration(s.duration_s)}
                  </span>
                </div>
                {s.alerts_count != null && s.alerts_count > 0 && (
                  <div className="text-[11px] text-muted-foreground inline-flex items-center gap-1 mt-0.5">
                    <Bell className="h-3 w-3" />
                    {s.alerts_count} alert
                  </div>
                )}
              </div>
              <span
                className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10.5px] font-medium rounded border shrink-0 ${badge.classes}`}
              >
                <badge.Icon className="h-3 w-3" />
                {badge.label}
              </span>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
