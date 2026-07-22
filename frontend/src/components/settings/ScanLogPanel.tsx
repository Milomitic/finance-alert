import { Activity, AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { useMemo, useState } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { QueryError } from "@/components/ui/query-error";
import { SectionTitle } from "@/components/ui/section-title";
import { useScanLog, type PhaseTiming, type ScanRunSummary } from "@/hooks/useScanLog";
import { cn } from "@/lib/utils";


/* ─── Scan log panel ────────────────────────────────────────────────────── *
 *
 * Recent scan_runs table with per-phase timing breakdown. Each row shows
 * one scan (most recent first) with a stacked horizontal bar visualizing
 * how the total wall-time was distributed across phases — like a
 * Gantt-strip but compressed into a single ~120px-wide line. Hover any
 * segment for the phase name + exact duration.
 *
 * KPI strip at top: count of last-N scans by status + average duration
 * for successful runs. Helps spot regressions ("yesterday avg 4min,
 * today 12min — what changed?") without staring at the table.
 */

export function ScanLogPanel() {
  const [kindFilter, setKindFilter] = useState<"" | "alerts_scan" | "score_recompute">("");
  const q = useScanLog(20, kindFilter || undefined);
  const runs = q.data?.runs ?? [];

  const kpis = useMemo(() => computeScanLogKpis(runs), [runs]);

  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={Activity}
          label="Log scan — performance per fase"
          right={
            <div className="flex items-center gap-2 text-xs">
              <span className="text-muted-foreground">Tipo:</span>
              <select
                value={kindFilter}
                onChange={(e) => setKindFilter(e.target.value as typeof kindFilter)}
                className="bg-background border rounded px-2 py-0.5 text-xs"
              >
                <option value="">Tutti</option>
                <option value="alerts_scan">Scan segnali</option>
                <option value="score_recompute">Score recompute</option>
              </select>
            </div>
          }
          className="mb-3"
        />

        {/* KPI strip — gives a one-glance health summary above the table */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
          <KpiCell label="Run mostrati" value={kpis.total.toString()} />
          <KpiCell
            label="Successi"
            value={`${kpis.success} (${kpis.successPct}%)`}
            tone={kpis.successPct >= 80 ? "pos" : kpis.successPct >= 50 ? "neutral" : "neg"}
          />
          <KpiCell
            label="Falliti"
            value={kpis.failed.toString()}
            tone={kpis.failed === 0 ? "pos" : "neg"}
          />
          <KpiCell
            label="Durata media (success)"
            value={kpis.avgDurationSec != null ? formatDuration(kpis.avgDurationSec) : "—"}
          />
        </div>

        {q.isLoading ? (
          <div className="py-6 text-center text-sm text-muted-foreground">
            Caricamento…
          </div>
        ) : q.isError ? (
          <div className="py-6">
            <QueryError message="del log scan" onRetry={q.refetch} isRetrying={q.isFetching} />
          </div>
        ) : runs.length === 0 ? (
          <div className="py-6 text-center text-sm text-muted-foreground">
            Nessuno scan registrato.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm tabular-nums">
              <thead className="bg-muted/30 text-muted-foreground border-b">
                <tr>
                  <th className="text-left px-2 py-2 font-semibold">Quando</th>
                  <th className="text-left px-2 py-2 font-semibold">Tipo</th>
                  <th className="text-left px-2 py-2 font-semibold">Stato</th>
                  <th className="text-right px-2 py-2 font-semibold">Durata</th>
                  <th className="text-left px-2 py-2 font-semibold w-[200px]">
                    Fasi
                  </th>
                  <th className="text-right px-2 py-2 font-semibold">Stock</th>
                  <th className="text-right px-2 py-2 font-semibold">Segnali</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <ScanLogRow key={r.id} run={r} />
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-[11px] text-muted-foreground italic">
              Il segmentato sotto "Fasi" mostra quanto tempo ha occupato
              ciascuna sotto-fase. Passa il mouse su un segmento per nome +
              durata. Auto-refresh ogni 30s.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function KpiCell({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "pos" | "neg" | "neutral";
}) {
  const toneCls =
    tone === "pos"
      ? "text-emerald-700 dark:text-emerald-400"
      : tone === "neg"
        ? "text-rose-700 dark:text-rose-400"
        : "text-foreground";
  return (
    <div className="rounded border bg-muted/30 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground/80">
        {label}
      </div>
      <div className={cn("text-base font-bold tabular-nums", toneCls)}>
        {value}
      </div>
    </div>
  );
}

function ScanLogRow({ run }: { run: ScanRunSummary }) {
  const started = new Date(run.started_at).toLocaleString("it-IT", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
  const totalSec = run.total_duration_sec;
  // Phase total used as denominator for the segmented bar widths. Falls
  // back to total_duration_sec when no phase data is available so the
  // "in progress" rows still show *something*.
  const phaseTotal = run.phases.reduce(
    (acc, p) => acc + (p.duration_sec ?? 0),
    0,
  ) || (totalSec ?? 0);

  return (
    <tr className="border-b border-border/40 hover:bg-muted/30 align-top">
      <td className="px-2 py-2 text-muted-foreground whitespace-nowrap">
        {started}
      </td>
      <td className="px-2 py-2">
        <span className="text-xs">
          {run.kind === "alerts_scan" ? "Alert" : "Score"}
          <span className="text-muted-foreground"> · {run.trigger}</span>
        </span>
      </td>
      <td className="px-2 py-2">
        {run.status === "success" && (
          <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
            <CheckCircle2 className="h-3.5 w-3.5" />
            success
          </span>
        )}
        {run.status === "failed" && (
          <span
            className="inline-flex items-center gap-1 text-rose-700 dark:text-rose-400"
            title={run.error_message ?? ""}
          >
            <AlertTriangle className="h-3.5 w-3.5" />
            failed
          </span>
        )}
        {run.status === "running" && (
          <span className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-400">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            in corso
          </span>
        )}
      </td>
      <td className="text-right px-2 py-2 font-semibold">
        {totalSec != null ? formatDuration(totalSec) : "—"}
      </td>
      <td className="px-2 py-2">
        {run.phases.length === 0 ? (
          <span className="text-muted-foreground italic text-xs">
            no data
          </span>
        ) : (
          <PhaseStrip phases={run.phases} totalSec={phaseTotal} />
        )}
      </td>
      <td className="text-right px-2 py-2">
        {run.stocks_scanned != null ? run.stocks_scanned : "—"}
      </td>
      <td className="text-right px-2 py-2">
        {run.alerts_fired != null && run.alerts_fired > 0 ? (
          <span className="text-emerald-700 dark:text-emerald-400 font-semibold">
            {run.alerts_fired}
          </span>
        ) : (
          <span className="text-muted-foreground">{run.alerts_fired ?? "—"}</span>
        )}
      </td>
    </tr>
  );
}

/* Color palette for phase segments — stable hash per phase name so the
 * same phase keeps the same color across runs. Tailwind colors handpicked
 * for contrast in both light/dark modes. */
const PHASE_COLORS = [
  "bg-blue-500/70",
  "bg-emerald-500/70",
  "bg-amber-500/70",
  "bg-rose-500/70",
  "bg-violet-500/70",
  "bg-cyan-500/70",
  "bg-fuchsia-500/70",
  "bg-lime-500/70",
] as const;

function colorForPhase(phase: string): string {
  let h = 0;
  for (let i = 0; i < phase.length; i++) {
    h = (h * 31 + phase.charCodeAt(i)) & 0xfffffff;
  }
  return PHASE_COLORS[h % PHASE_COLORS.length];
}

function PhaseStrip({
  phases,
  totalSec,
}: {
  phases: PhaseTiming[];
  totalSec: number;
}) {
  const safeTotal = totalSec > 0 ? totalSec : 1;
  return (
    <div className="space-y-1">
      <div className="flex h-2 rounded overflow-hidden bg-muted">
        {phases.map((p, i) => {
          const dur = p.duration_sec ?? 0;
          const widthPct = (dur / safeTotal) * 100;
          if (widthPct < 0.5) return null; // skip dust segments
          return (
            <div
              key={i}
              className={colorForPhase(p.phase)}
              style={{ width: `${widthPct}%` }}
              title={`${p.phase} · ${formatDuration(dur)}`}
            />
          );
        })}
      </div>
      {/* Top-3 phase chips — at-a-glance "where did the time go?" */}
      <div className="flex flex-wrap gap-1 text-[10px]">
        {phases
          .slice()
          .sort((a, b) => (b.duration_sec ?? 0) - (a.duration_sec ?? 0))
          .slice(0, 3)
          .map((p, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 rounded bg-muted/60 px-1.5 py-0.5"
              title={p.phase}
            >
              <span className={cn("h-1.5 w-1.5 rounded-full", colorForPhase(p.phase))} />
              <span className="truncate max-w-[80px]">{shortPhase(p.phase)}</span>
              <span className="font-semibold tabular-nums text-muted-foreground">
                {formatDuration(p.duration_sec ?? 0)}
              </span>
            </span>
          ))}
      </div>
    </div>
  );
}

function shortPhase(phase: string): string {
  // Trim the "fetching:"/"evaluating:" prefix for a denser chip text.
  return phase.replace(/^fetching:/, "").replace(/^evaluating:/, "");
}

function formatDuration(sec: number): string {
  if (sec < 1) return `${Math.round(sec * 1000)}ms`;
  if (sec < 60) return `${sec.toFixed(1)}s`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec - m * 60);
  return s === 0 ? `${m}m` : `${m}m ${s}s`;
}

function computeScanLogKpis(runs: ScanRunSummary[]): {
  total: number;
  success: number;
  failed: number;
  successPct: number;
  avgDurationSec: number | null;
} {
  const total = runs.length;
  const success = runs.filter((r) => r.status === "success").length;
  const failed = runs.filter((r) => r.status === "failed").length;
  const successPct = total > 0 ? Math.round((success / total) * 100) : 0;
  const successDurations = runs
    .filter((r) => r.status === "success" && r.total_duration_sec != null)
    .map((r) => r.total_duration_sec as number);
  const avgDurationSec =
    successDurations.length > 0
      ? successDurations.reduce((a, b) => a + b, 0) / successDurations.length
      : null;
  return { total, success, failed, successPct, avgDurationSec };
}
