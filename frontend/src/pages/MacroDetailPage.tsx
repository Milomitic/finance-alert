import { ArrowLeft, Building2, Globe } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { MacroRelease } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CardSkeleton } from "@/components/ui/card-skeleton";
import { useMacroDetail } from "@/hooks/useCalendar";
import { regionFlagAsset, regionLabel } from "@/lib/calendarMeta";
import { cn } from "@/lib/utils";

/* ─── /macro/:seriesId — Investing-style indicator detail page ─────────── *
 *
 * Layout decisions (faithful to the user's reference screenshot):
 *  1. Sticky-ish header strip: ATTUALE · PREVISTO · PRECEDENTE side by
 *     side, with the actual styled bigger and tinted by surprise sign.
 *     This is the "primary" data cell — what the user comes here for.
 *  2. Two-column body: description text (left, narrative) +  metadata
 *     card (right, importance/region/currency/source).
 *  3. Range tabs (1A / 5A / MAX) above a recharts BarChart of the full
 *     observation history. Bars are positive/negative-tinted. A zero
 *     reference line splits the field for visual anchor.
 *  4. History table below the chart: Data · Periodo · Attuale · Previsto
 *     · Precedente. Expected stays "—" for past rows (we don't backfill
 *     consensus — see API docstring).
 */

const RANGES = [
  { id: "1y", label: "1A", years: 1 },
  { id: "5y", label: "5A", years: 5 },
  { id: "max", label: "MAX", years: null },
] as const;
type RangeId = (typeof RANGES)[number]["id"];

export default function MacroDetailPage() {
  const { seriesId } = useParams<{ seriesId: string }>();
  const navigate = useNavigate();
  const id = seriesId ? parseInt(seriesId, 10) : undefined;
  const detail = useMacroDetail(id);

  const [range, setRange] = useState<RangeId>("5y");

  const filteredHistory = useMemo(() => {
    if (!detail.data) return [];
    const cfg = RANGES.find((r) => r.id === range);
    if (!cfg || cfg.years === null) return detail.data.history;
    const cutoff = new Date();
    cutoff.setFullYear(cutoff.getFullYear() - cfg.years);
    return detail.data.history.filter(
      (h) => new Date(h.release_date) >= cutoff,
    );
  }, [detail.data, range]);

  // Chart data: oldest → newest for natural left-to-right reading.
  // Recharts iterates in array order, so this is the only place we
  // reverse the history (the API returns newest-first).
  const chartData = useMemo(
    () =>
      filteredHistory
        .slice()
        .reverse()
        .filter((r) => r.actual_value != null)
        .map((r) => ({
          date: r.release_date,
          value: r.actual_value as number,
          period: r.period_label ?? "",
        })),
    [filteredHistory],
  );

  if (id == null || Number.isNaN(id)) {
    return (
      <div className="p-8 text-sm text-muted-foreground">
        Series id mancante o non valido.
      </div>
    );
  }

  if (detail.isLoading) {
    // Macro indicator detail = header KPIs + time-series chart. The
    // skeleton mirrors that two-block layout (was a spinner-line).
    return (
      <div className="space-y-3">
        <CardSkeleton rows={3} className="h-[140px]" />
        <CardSkeleton label="SERIE STORICA" rows={10} strongHeader className="h-[460px]" />
      </div>
    );
  }

  if (detail.isError || !detail.data) {
    return (
      <div className="p-8">
        <div className="text-sm text-rose-600 dark:text-rose-400">
          Indicatore non trovato.
        </div>
        <Button
          variant="outline"
          size="sm"
          className="mt-3"
          onClick={() => navigate(-1)}
        >
          <ArrowLeft className="h-4 w-4 mr-1" /> Indietro
        </Button>
      </div>
    );
  }

  const d = detail.data;
  const flagAsset = regionFlagAsset(d.region);
  const unit = d.unit ?? "";
  const latest = d.latest;

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6">
      {/* Header bar with back link + indicator title + flag */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
          <ArrowLeft className="h-4 w-4 mr-1" /> Indietro
        </Button>
        <div className="flex items-center gap-2 flex-1 min-w-0">
          {flagAsset ? (
            <img
              src={`/flags/${flagAsset}.svg`}
              alt={d.region}
              width={28}
              height={20}
              style={{ width: "28px", height: "20px", objectFit: "cover" }}
              className="rounded ring-1 ring-border shrink-0"
            />
          ) : null}
          <h1 className="text-xl font-semibold truncate">{d.label}</h1>
          <ImportanceStars importance={d.importance} />
        </div>
      </div>

      {/* Top KPI strip — the primary data the page is built around.
          Mirrors Investing's "Ultime Notizie [date] · Attuale · Previsto
          · Precedente" header where the latest release dominates and the
          three values sit on a single visual line. */}
      <Card>
        <CardContent className="p-5">
          <div className="flex items-baseline gap-3 mb-4 flex-wrap">
            <div className="text-xs uppercase tracking-wider text-muted-foreground">
              Ultima release
            </div>
            <div className="text-sm font-medium tabular-nums">
              {latest ? formatMacroDate(latest.release_date) : "—"}
            </div>
            {latest?.period_label && (
              <div className="text-sm text-muted-foreground tabular-nums">
                ({latest.period_label})
              </div>
            )}
          </div>

          <div className="grid grid-cols-3 gap-6 sm:gap-8">
            <KpiCell
              label="Attuale"
              value={latest?.actual_value}
              unit={unit}
              size="xl"
              tone={surpriseTone(latest)}
            />
            <KpiCell
              label="Previsto"
              value={latest?.expected_value}
              unit={unit}
              size="lg"
            />
            <KpiCell
              label="Precedente"
              value={latest?.previous_value}
              unit={unit}
              size="lg"
            />
          </div>
        </CardContent>
      </Card>

      {/* Two-column body: description (left, wide) + metadata (right) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Cos'è questo indicatore</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-foreground/85 leading-relaxed whitespace-pre-line">
              {d.description ?? "Descrizione non disponibile per questo indicatore."}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Metadati</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <MetaRow label="Paese" value={regionLabel(d.region)} icon={<Globe className="h-3.5 w-3.5" />} />
            <MetaRow label="Valuta" value={d.currency ?? "—"} />
            <MetaRow
              label="Importanza"
              value={
                d.importance === "high"
                  ? "Alta"
                  : d.importance === "medium"
                    ? "Media"
                    : "Bassa"
              }
            />
            <MetaRow
              label="Fonte"
              value={d.source ?? "—"}
              icon={<Building2 className="h-3.5 w-3.5" />}
            />
            <MetaRow label="ID FRED" value={d.fred_series_id} mono />
            {d.upcoming.length > 0 && (
              <MetaRow
                label="Prossime release"
                value={d.upcoming.slice(0, 3).map(formatMacroDate).join(" · ")}
              />
            )}
          </CardContent>
        </Card>
      </div>

      {/* Chart + range tabs */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-base">Storico release</CardTitle>
          <div className="flex gap-1">
            {RANGES.map((r) => (
              <button
                key={r.id}
                type="button"
                onClick={() => setRange(r.id)}
                className={cn(
                  "px-2.5 py-1 text-xs rounded font-medium transition-colors",
                  r.id === range
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted/50 text-muted-foreground hover:bg-muted",
                )}
              >
                {r.label}
              </button>
            ))}
          </div>
        </CardHeader>
        <CardContent>
          {chartData.length === 0 ? (
            <div className="h-[280px] flex items-center justify-center text-sm text-muted-foreground">
              Nessun dato nel range selezionato.
            </div>
          ) : (
            <div className="h-[320px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={chartData}
                  margin={{ top: 8, right: 12, left: 4, bottom: 4 }}
                >
                  <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tickFormatter={(v: string) => formatMacroDate(v)}
                    tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                    axisLine={{ stroke: "hsl(var(--border))" }}
                    tickLine={{ stroke: "hsl(var(--border))" }}
                    interval="preserveStartEnd"
                    minTickGap={40}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                    axisLine={{ stroke: "hsl(var(--border))" }}
                    tickLine={{ stroke: "hsl(var(--border))" }}
                    tickFormatter={(v: number) => formatMacroValue(v, unit)}
                    width={60}
                  />
                  <Tooltip
                    cursor={{ fill: "hsl(var(--muted) / 0.4)" }}
                    content={<ChartTooltip unit={unit} />}
                  />
                  <ReferenceLine y={0} stroke="hsl(var(--border))" />
                  <Bar dataKey="value" radius={[2, 2, 0, 0]}>
                    {chartData.map((p, i) => (
                      <Cell
                        key={i}
                        fill={
                          p.value >= 0
                            ? "hsl(var(--primary))"
                            : "hsl(var(--destructive))"
                        }
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>

      {/* History table — Investing's "Storico" */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Tabella storica</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-sm tabular-nums">
            <thead>
              <tr className="text-xs uppercase tracking-wider text-muted-foreground border-b border-border">
                <th className="text-left font-semibold pb-2">Data di rilascio</th>
                <th className="text-left font-semibold pb-2 hidden sm:table-cell">Periodo</th>
                <th className="text-right font-semibold pb-2">Attuale</th>
                <th className="text-right font-semibold pb-2">Previsto</th>
                <th className="text-right font-semibold pb-2">Precedente</th>
              </tr>
            </thead>
            <tbody>
              {filteredHistory.slice(0, 50).map((r) => (
                <tr
                  key={r.release_date}
                  className="border-b border-border/40 hover:bg-muted/30 transition-colors"
                >
                  <td className="py-2 text-left">{formatMacroDate(r.release_date)}</td>
                  <td className="py-2 text-left text-muted-foreground hidden sm:table-cell">
                    {r.period_label ?? "—"}
                  </td>
                  <td className="py-2 text-right font-semibold">
                    {r.actual_value != null ? formatMacroValue(r.actual_value, unit) : "—"}
                  </td>
                  <td className="py-2 text-right text-muted-foreground">
                    {r.expected_value != null ? formatMacroValue(r.expected_value, unit) : "—"}
                  </td>
                  <td className="py-2 text-right">
                    {r.previous_value != null ? formatMacroValue(r.previous_value, unit) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {filteredHistory.length > 50 && (
            <div className="text-xs text-muted-foreground mt-2 text-center">
              Mostrate 50 release più recenti del range selezionato (totale {filteredHistory.length}).
            </div>
          )}
        </CardContent>
      </Card>

      <div className="flex justify-center pb-6">
        <Link to="/calendar" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
          ← Torna al calendario
        </Link>
      </div>
    </div>
  );
}

/* ─── Sub-components ───────────────────────────────────────────────────── */

function KpiCell({
  label,
  value,
  unit,
  size = "lg",
  tone,
}: {
  label: string;
  value: number | null | undefined;
  unit: string;
  size?: "lg" | "xl";
  tone?: "pos" | "neg" | "neutral";
}) {
  const sizeCls = size === "xl" ? "text-3xl" : "text-2xl";
  const toneCls =
    tone === "pos"
      ? "text-emerald-600 dark:text-emerald-400"
      : tone === "neg"
        ? "text-rose-600 dark:text-rose-400"
        : "text-foreground";
  return (
    <div className="flex flex-col gap-1 min-w-0">
      <div className="text-xs uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className={cn(sizeCls, "font-bold tabular-nums leading-tight", toneCls)}>
        {value != null ? formatMacroValue(value, unit) : "—"}
      </div>
    </div>
  );
}

function MetaRow({
  label,
  value,
  icon,
  mono,
}: {
  label: string;
  value: string;
  icon?: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-xs uppercase tracking-wider text-muted-foreground inline-flex items-center gap-1">
        {icon}
        {label}
      </span>
      <span className={cn("text-right truncate", mono && "font-mono text-xs")}>
        {value}
      </span>
    </div>
  );
}

function ImportanceStars({ importance }: { importance: "high" | "medium" | "low" }) {
  const filled = importance === "high" ? 3 : importance === "medium" ? 2 : 1;
  return (
    <span
      className="inline-flex items-center gap-0.5 ml-2"
      title={`Importanza: ${importance}`}
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className={cn(
            "text-base leading-none",
            i < filled ? "text-amber-500" : "text-muted-foreground/30",
          )}
        >
          ★
        </span>
      ))}
    </span>
  );
}

interface ChartTooltipPayloadEntry {
  payload: { date: string; value: number; period: string };
}

function ChartTooltip({
  active,
  payload,
  unit,
}: {
  active?: boolean;
  payload?: ChartTooltipPayloadEntry[];
  unit: string;
}) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded border bg-popover px-2.5 py-1.5 text-xs shadow-lg">
      <div className="font-medium">{formatMacroDate(p.date)}</div>
      {p.period && <div className="text-muted-foreground tabular-nums">{p.period}</div>}
      <div className="font-bold tabular-nums mt-0.5">
        {formatMacroValue(p.value, unit)}
      </div>
    </div>
  );
}

/* ─── helpers (mirror DayDetailPanel internals) ────────────────────────── */

function surpriseTone(r: MacroRelease | null | undefined): "pos" | "neg" | "neutral" {
  if (!r || r.actual_value == null || r.expected_value == null) return "neutral";
  if (r.actual_value > r.expected_value) return "pos";
  if (r.actual_value < r.expected_value) return "neg";
  return "neutral";
}

function formatMacroDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("it-IT", {
    day: "numeric",
    month: "short",
    year: "2-digit",
  });
}

function formatMacroValue(v: number, unit: string): string {
  if (!Number.isFinite(v)) return "—";
  if (unit === "pct" || unit === "yield") {
    return `${v.toFixed(2)}%`;
  }
  if (unit === "level") {
    const abs = Math.abs(v);
    if (abs >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
    if (abs >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
    if (abs >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
    if (abs >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
    return v.toFixed(0);
  }
  if (unit === "index") return v.toFixed(1);
  return v.toFixed(2);
}
