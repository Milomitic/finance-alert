import {
  AlertTriangle,
  CheckCircle2,
  HeartPulse,
  Loader2,
  XCircle,
} from "lucide-react";
import { useState } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import {
  useKpiMonitor,
  type KpiFlag,
  type KpiSignalPopulation,
  type KpiSnapshot,
  type KpiScanMetrics,
} from "@/hooks/useKpiMonitor";
import { cn } from "@/lib/utils";

const HZ_IT: Record<string, string> = { short: "Breve", medium: "Medio", long: "Lungo" };
const HZ_ORDER = ["short", "medium", "long"];
const CONF_ORDER = ["60-69", "70-79", "80-89", "90-100"];

/* ─── EngineHealthPanel — "Salute motori" ───────────────────────────────── *
 *
 * Continuous-improvement monitoring surface (Fase B). Reads the KPI series
 * captured at scan-end + daily cron and renders:
 *   1. Flags — a triage list (errors → warns → ok), already sorted backend-side.
 *   2. KPI strip — active-signal count, tone split, confluence health.
 *   3. Population — current distribution by horizon + confidence bucket.
 *   4. Scan trend — alerts fired across the last N scans (mini sparkbars).
 *
 * Everything is best-effort: an empty series (engine never scanned, or cron
 * never ran) degrades to explanatory empty states rather than blanks.
 */
export function EngineHealthPanel() {
  const [days, setDays] = useState(90);
  const q = useKpiMonitor(days);
  const data = q.data;

  const latestScan = data?.scans[0];
  const latestRollup = data?.rollups[0];
  // Prefer the freshest population: scan rows are captured more often than
  // the daily rollup, so the scan snapshot is usually the most recent shape.
  const pop: KpiSignalPopulation | undefined =
    latestScan?.metrics.signals ?? latestRollup?.metrics.signals;
  const confl = latestRollup?.metrics.confluence;

  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={HeartPulse}
          label="Salute motori — monitoraggio continuo"
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
              </select>
            </div>
          }
          className="mb-3"
        />

        {q.isLoading ? (
          <div className="py-8 text-center text-sm text-muted-foreground inline-flex items-center gap-2 justify-center w-full">
            <Loader2 className="h-4 w-4 animate-spin" />
            Carico KPI…
          </div>
        ) : (
          <div className="space-y-4">
            {/* 1. Flags triage */}
            <div className="space-y-1.5">
              {(data?.flags ?? []).map((f) => (
                <FlagRow key={f.code} flag={f} />
              ))}
            </div>

            {/* 2. KPI strip */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <StatCell label="Segnali attivi" value={pop ? String(pop.total) : "—"} />
              <StatCell
                label="Bull / Bear"
                value={
                  pop
                    ? `${pop.by_tone.bull ?? 0} / ${pop.by_tone.bear ?? 0}`
                    : "—"
                }
              />
              <StatCell
                label="Confluenze"
                value={confl ? String(confl.n_clusters) : "—"}
                hint={
                  confl?.multi_horizon_rate != null
                    ? `${(confl.multi_horizon_rate * 100).toFixed(0)}% multi-orizz.`
                    : undefined
                }
              />
              <StatCell
                label="Contese"
                value={
                  confl?.contested_rate != null
                    ? `${(confl.contested_rate * 100).toFixed(0)}%`
                    : "—"
                }
                tone={
                  confl?.contested_rate != null && confl.contested_rate > 0.3
                    ? "warn"
                    : undefined
                }
              />
            </div>

            {/* 3. Population distribution */}
            {pop && pop.total > 0 && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Distribution
                  title="Per orizzonte"
                  dist={pop.by_horizon}
                  order={HZ_ORDER}
                  labels={HZ_IT}
                  total={pop.total}
                />
                <Distribution
                  title="Per confidenza"
                  dist={pop.by_confidence}
                  order={CONF_ORDER}
                  total={pop.total}
                />
              </div>
            )}

            {/* 4. Scan trend */}
            {data && data.scans.length > 0 && <ScanTrend scans={data.scans} />}

            <p className="text-[11px] text-muted-foreground italic">
              KPI raccolti a fine scan (popolazione segnali + fonti dati) e dal
              rollup giornaliero (calibrazione + confluenza). I flag in cima
              segnalano scan a vuoto, fonti degradate o calibrazione immatura.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function FlagRow({ flag }: { flag: KpiFlag }) {
  const cfg =
    flag.level === "error"
      ? { Icon: XCircle, cls: "text-rose-700 dark:text-rose-400 bg-rose-50 dark:bg-rose-950/30 border-rose-200 dark:border-rose-900/50" }
      : flag.level === "warn"
        ? { Icon: AlertTriangle, cls: "text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-900/50" }
        : { Icon: CheckCircle2, cls: "text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-900/50" };
  const { Icon } = cfg;
  return (
    <div className={cn("flex items-start gap-2 rounded-md border px-2.5 py-1.5", cfg.cls)}>
      <Icon className="h-4 w-4 shrink-0 mt-0.5" />
      <div className="min-w-0">
        <div className="text-sm font-semibold leading-tight">{flag.title}</div>
        <div className="text-xs text-muted-foreground leading-snug">{flag.detail}</div>
      </div>
    </div>
  );
}

function StatCell({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "warn";
}) {
  return (
    <div className="rounded border bg-muted/30 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground/80">
        {label}
      </div>
      <div
        className={cn(
          "text-base font-bold tabular-nums",
          tone === "warn" ? "text-amber-700 dark:text-amber-400" : "text-foreground",
        )}
      >
        {value}
      </div>
      {hint && <div className="text-[10px] text-muted-foreground tabular-nums">{hint}</div>}
    </div>
  );
}

/* Horizontal proportion bars for a distribution (Record<key, count>). */
function Distribution({
  title,
  dist,
  order,
  labels,
  total,
}: {
  title: string;
  dist: Record<string, number>;
  order: string[];
  labels?: Record<string, string>;
  total: number;
}) {
  const safe = total > 0 ? total : 1;
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-1.5">
        {title}
      </div>
      <div className="space-y-1.5">
        {order.map((k) => {
          const n = dist[k] ?? 0;
          const pct = (n / safe) * 100;
          return (
            <div key={k} className="flex items-center gap-2 text-xs">
              <span className="w-14 shrink-0 text-muted-foreground">
                {labels?.[k] ?? k}
              </span>
              <div className="flex-1 h-2 rounded bg-muted overflow-hidden">
                <div className="h-full bg-blue-500/70" style={{ width: `${pct}%` }} />
              </div>
              <span className="w-8 shrink-0 text-right font-semibold tabular-nums">
                {n}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* Mini vertical sparkbars of alerts_fired across recent scans (oldest→newest,
   left→right). Hover a bar for the timestamp + count. */
function ScanTrend({ scans }: { scans: KpiSnapshot<KpiScanMetrics>[] }) {
  // scans arrive newest-first; reverse to a chronological left→right strip and
  // cap at the last ~30 to keep the bars readable.
  const series = scans.slice(0, 30).reverse();
  const maxFired = Math.max(1, ...series.map((s) => s.metrics.alerts_fired ?? 0));
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-1.5">
        Segnali per scan — ultimi {series.length}
      </div>
      <div className="flex items-end gap-0.5 h-16">
        {series.map((s) => {
          const fired = s.metrics.alerts_fired ?? 0;
          const hPct = (fired / maxFired) * 100;
          const when = new Date(s.captured_at).toLocaleString("it-IT", {
            day: "2-digit",
            month: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
          });
          return (
            <div
              key={s.id}
              className="flex-1 min-w-[3px] bg-emerald-500/70 hover:bg-emerald-500 rounded-t"
              style={{ height: `${Math.max(hPct, 2)}%` }}
              title={`${when} · ${fired} segnali · ${s.metrics.stocks_scanned ?? "?"} titoli`}
            />
          );
        })}
      </div>
    </div>
  );
}
