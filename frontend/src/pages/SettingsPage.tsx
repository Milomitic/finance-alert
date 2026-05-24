import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Database,
  Loader2,
  RefreshCw,
  Settings as SettingsIcon,
  Target,
  TrendingUp,
} from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import {
  useCatalogStatus,
  useTriggerCatalogRefresh,
} from "@/hooks/useCatalogStatus";
import { useCalibration, useRulePerformance } from "@/hooks/useRulePerformance";
import { useScanLog, type PhaseTiming, type ScanRunSummary } from "@/hooks/useScanLog";
import { getAlertKindMeta } from "@/lib/alertMeta";
import { getIndexMeta } from "@/lib/indexMeta";
import { cn } from "@/lib/utils";

/* ─── SettingsPage — /settings route ────────────────────────────────────── *
 *
 * Admin / diagnostic surface. Two main panels:
 *   - Rule effectiveness (forward-return stats per rule.kind over
 *     1d / 5d / 20d windows).
 *   - Catalog refresh status (per-index last-run state + manual
 *     trigger).
 *
 * Was a placeholder ("Disponibile nelle prossime fasi") in the
 * sidebar for the entire 3A-3C lifetime; ships in Fase 3E.
 */
export default function SettingsPage() {
  return (
    <div className="space-y-5 max-w-6xl">
      <header className="space-y-1">
        <div className="flex items-center gap-2 text-[10px] font-mono font-semibold uppercase tracking-[0.22em] text-muted-foreground">
          <SettingsIcon className="h-3 w-3" />
          <span>Amministrazione · diagnostica</span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight leading-tight">
          Impostazioni
        </h1>
        <p className="text-sm text-muted-foreground max-w-2xl">
          Statistiche di efficacia dei segnali e stato dei refresh
          catalogo per indice.
        </p>
      </header>

      <RulePerformancePanel />
      <CalibrationPanel />
      <ScanLogPanel />
      <CatalogRefreshPanel />
    </div>
  );
}

/* ─── Rule performance panel ────────────────────────────────────────────── */

function RulePerformancePanel() {
  const [days, setDays] = useState(90);
  const q = useRulePerformance(days);
  const items = q.data?.items ?? [];

  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={TrendingUp}
          label="Efficacia segnali — forward return"
          right={
            <div className="flex items-center gap-2 text-xs">
              <span className="text-muted-foreground">Finestra:</span>
              <select
                value={days}
                onChange={(e) => setDays(Number(e.target.value))}
                className="bg-background border rounded px-2 py-0.5 text-xs"
              >
                <option value={30}>30 giorni</option>
                <option value={90}>90 giorni</option>
                <option value={180}>180 giorni</option>
                <option value={365}>1 anno</option>
              </select>
            </div>
          }
          className="mb-3"
        />

        {q.isLoading ? (
          <div className="py-8 text-center text-sm text-muted-foreground inline-flex items-center gap-2 justify-center w-full">
            <Loader2 className="h-4 w-4 animate-spin" />
            Calcolo statistiche…
          </div>
        ) : items.length === 0 ? (
          <div className="py-8 text-center text-sm text-muted-foreground">
            Nessun alert nel periodo — esegui uno scan per generare
            dati di efficacia.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm tabular-nums">
              <thead className="bg-muted/30 text-muted-foreground border-b">
                <tr className="text-base">
                  <th className="text-left px-3 py-2 font-semibold">Segnale</th>
                  <th className="text-right px-3 py-2 font-semibold">N</th>
                  {[1, 5, 20].flatMap((w) => [
                    <th key={`m${w}`} className="text-right px-3 py-2 font-semibold">
                      Media {w}d
                    </th>,
                    <th key={`h${w}`} className="text-right px-3 py-2 font-semibold">
                      Hit {w}d
                    </th>,
                  ])}
                </tr>
              </thead>
              <tbody>
                {items.map((row) => {
                  const meta = getAlertKindMeta(row.rule_kind);
                  const Icon = meta.icon;
                  return (
                    <tr
                      key={row.rule_kind}
                      className="border-b border-border/40 hover:bg-muted/30"
                    >
                      <td className="px-3 py-2">
                        <span className="inline-flex items-center gap-2">
                          <Icon className="h-3.5 w-3.5 shrink-0" />
                          <span className="font-semibold">{meta.label}</span>
                          <span
                            className={cn(
                              "px-1.5 py-px rounded text-[10px] uppercase tracking-wider font-semibold",
                              row.tone === "bullish"
                                ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200"
                                : row.tone === "bearish"
                                  ? "bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-200"
                                  : "bg-muted text-muted-foreground",
                            )}
                          >
                            {row.tone}
                          </span>
                        </span>
                      </td>
                      <td className="text-right px-3 py-2 font-bold">
                        {row.total_alerts}
                      </td>
                      {[1, 5, 20].flatMap((w) => {
                        const s = row.stats[String(w)];
                        return [
                          <td
                            key={`m${w}-${row.rule_kind}`}
                            className={cn(
                              "text-right px-3 py-2 font-semibold",
                              s?.mean_pct == null
                                ? "text-muted-foreground"
                                : s.mean_pct > 0
                                  ? "text-emerald-700 dark:text-emerald-400"
                                  : s.mean_pct < 0
                                    ? "text-rose-700 dark:text-rose-400"
                                    : "",
                            )}
                            title={
                              s?.median_pct != null
                                ? `Mediana ${s.median_pct.toFixed(2)}%`
                                : undefined
                            }
                          >
                            {s?.mean_pct == null
                              ? "—"
                              : `${s.mean_pct >= 0 ? "+" : ""}${s.mean_pct.toFixed(2)}%`}
                          </td>,
                          <td
                            key={`h${w}-${row.rule_kind}`}
                            className={cn(
                              "text-right px-3 py-2 font-semibold",
                              s?.hit_rate == null
                                ? "text-muted-foreground"
                                : s.hit_rate >= 0.55
                                  ? "text-emerald-700 dark:text-emerald-400"
                                  : s.hit_rate >= 0.45
                                    ? ""
                                    : "text-rose-700 dark:text-rose-400",
                            )}
                            title={
                              s?.count != null
                                ? `${s.count} osservazioni`
                                : undefined
                            }
                          >
                            {s?.hit_rate == null
                              ? "—"
                              : `${(s.hit_rate * 100).toFixed(0)}%`}
                          </td>,
                        ];
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="mt-2 text-[11px] text-muted-foreground italic">
              "Hit" = % di alert con direzione coerente con il tono del
              segnale entro la finestra (bullish → ritorno positivo,
              bearish → negativo). I segnali neutri non hanno hit-rate.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

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

function ScanLogPanel() {
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
                <option value="alerts_scan">Alert scan</option>
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
                  <th className="text-right px-2 py-2 font-semibold">Alert</th>
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

/* ─── Catalog refresh panel ─────────────────────────────────────────────── */

function CatalogRefreshPanel() {
  const status = useCatalogStatus();
  const trigger = useTriggerCatalogRefresh();
  const indices = status.data?.indices ?? [];

  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={Database}
          label="Stato refresh catalogo"
          right={
            <Button
              size="sm"
              variant="outline"
              disabled={trigger.isPending}
              onClick={() => trigger.mutate(null)}
            >
              <RefreshCw
                className={cn(
                  "h-3.5 w-3.5 mr-1",
                  trigger.isPending && "animate-spin",
                )}
              />
              Refresh tutti
            </Button>
          }
          className="mb-3"
        />

        {status.isLoading ? (
          <div className="py-6 text-center text-sm text-muted-foreground">
            Caricamento…
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm tabular-nums">
              <thead className="bg-muted/30 text-muted-foreground border-b">
                <tr className="text-base">
                  <th className="text-left px-3 py-2 font-semibold">Indice</th>
                  <th className="text-left px-3 py-2 font-semibold">Stato</th>
                  <th className="text-right px-3 py-2 font-semibold">
                    Ultimo refresh
                  </th>
                  <th className="text-right px-3 py-2 font-semibold">+/-/=</th>
                  <th className="text-right px-3 py-2 font-semibold"></th>
                </tr>
              </thead>
              <tbody>
                {indices.map((idx) => {
                  const meta = getIndexMeta(idx.index_code);
                  const completed = idx.last_completed_at
                    ? new Date(idx.last_completed_at).toLocaleString("it-IT", {
                        day: "2-digit",
                        month: "2-digit",
                        year: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                      })
                    : "—";
                  return (
                    <tr
                      key={idx.index_code}
                      className="border-b border-border/40 hover:bg-muted/30"
                    >
                      <td className="px-3 py-2">
                        <span className="inline-flex items-center gap-2">
                          {meta.countryCode && (
                            <img
                              src={`/flags/${meta.countryCode}.svg`}
                              alt={meta.country}
                              width={20}
                              height={14}
                              style={{ width: "20px", height: "14px", objectFit: "cover" }}
                              className="rounded-[1px] ring-1 ring-border/60 shrink-0"
                              aria-hidden
                            />
                          )}
                          <span className="font-semibold">{meta.displayCode}</span>
                          <span className="text-xs text-muted-foreground">
                            {meta.fullName}
                          </span>
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        {idx.last_status === "success" && (
                          <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            success
                          </span>
                        )}
                        {idx.last_status === "failed" && (
                          <span
                            className="inline-flex items-center gap-1 text-rose-700 dark:text-rose-400"
                            title={idx.error_message ?? ""}
                          >
                            <AlertTriangle className="h-3.5 w-3.5" />
                            failed
                          </span>
                        )}
                        {idx.last_status === "in_progress" && (
                          <span className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-400">
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            in corso
                          </span>
                        )}
                        {idx.last_status == null && (
                          <span className="text-muted-foreground">mai</span>
                        )}
                      </td>
                      <td className="text-right px-3 py-2 text-muted-foreground">
                        {completed}
                      </td>
                      <td className="text-right px-3 py-2">
                        {idx.stocks_added != null ? (
                          <span>
                            <span className="text-emerald-700 dark:text-emerald-400">
                              +{idx.stocks_added}
                            </span>
                            {" / "}
                            <span className="text-blue-700 dark:text-blue-400">
                              ~{idx.stocks_updated ?? 0}
                            </span>
                            {" / "}
                            <span className="text-rose-700 dark:text-rose-400">
                              -{idx.stocks_removed ?? 0}
                            </span>
                          </span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="text-right px-3 py-2">
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={trigger.isPending}
                          onClick={() => trigger.mutate(idx.index_code)}
                          title={`Refresh ${meta.displayCode}`}
                        >
                          <RefreshCw className="h-3.5 w-3.5" />
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="mt-2 text-[11px] text-muted-foreground italic">
              I refresh leggono Wikipedia per aggiornare i constituent
              di ciascun indice. "+/~/-": aggiunti / aggiornati /
              rimossi vs il run precedente.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ─── Calibration panel ─────────────────────────────────────────────────── */

function CalibrationPanel() {
  const [horizon, setHorizon] = useState(20);
  const q = useCalibration(365, horizon);
  const c = q.data;
  const matured = c ? c.by_confidence.reduce((a, b) => a + b.count, 0) : 0;
  const pct = (v: number | null) => (v == null ? "-" : `${(v * 100).toFixed(0)}%`);
  const ret = (v: number | null) => (v == null ? "-" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`);

  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={Target}
          label="Calibrazione - confidenza vs esito reale"
          right={
            <div className="flex items-center gap-2 text-xs">
              <span className="text-muted-foreground">Orizzonte:</span>
              <select
                value={horizon}
                onChange={(e) => setHorizon(Number(e.target.value))}
                className="bg-background border rounded px-2 py-0.5 text-xs"
              >
                <option value={5}>5 giorni</option>
                <option value={10}>10 giorni</option>
                <option value={20}>20 giorni</option>
              </select>
            </div>
          }
          className="mb-3"
        />
        {q.isLoading ? (
          <div className="py-8 text-center text-sm text-muted-foreground inline-flex items-center gap-2 justify-center w-full">
            <Loader2 className="h-4 w-4 animate-spin" />
            Calcolo calibrazione...
          </div>
        ) : matured === 0 ? (
          <div className="py-6 text-center text-sm text-muted-foreground">
            Esiti non ancora maturi: la calibrazione richiede circa {horizon} giorni di
            borsa dopo ogni segnale. Si popolera man mano che gli alert maturano.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <CalTable title="Per confidenza" rows={c!.by_confidence} pct={pct} ret={ret} />
            <CalTable title="Per natura" rows={c!.by_nature} pct={pct} ret={ret} />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function CalTable({
  title,
  rows,
  pct,
  ret,
}: {
  title: string;
  rows: { label: string; count: number; hit_rate: number | null; mean_pct: number | null }[];
  pct: (v: number | null) => string;
  ret: (v: number | null) => string;
}) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-1">
        {title}
      </div>
      <table className="w-full text-sm tabular-nums">
        <thead className="text-muted-foreground border-b">
          <tr>
            <th className="text-left px-2 py-1 font-semibold">Gruppo</th>
            <th className="text-right px-2 py-1 font-semibold">N</th>
            <th className="text-right px-2 py-1 font-semibold">Hit</th>
            <th className="text-right px-2 py-1 font-semibold">Media</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className="border-b border-border/40">
              <td className="px-2 py-1">{r.label}</td>
              <td className="px-2 py-1 text-right">{r.count || "-"}</td>
              <td className="px-2 py-1 text-right font-semibold">{r.count ? pct(r.hit_rate) : "-"}</td>
              <td className="px-2 py-1 text-right">{r.count ? ret(r.mean_pct) : "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
