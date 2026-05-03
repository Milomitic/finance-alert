import { ArrowDownRight, ArrowUpRight, CalendarClock } from "lucide-react";
import { useMemo } from "react";
import {
  Bar, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import type {
  FundamentalsAnnual, FundamentalsEarnings, FundamentalsQuarterly,
} from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useStockFundamentals } from "@/hooks/useStockFundamentals";
import { cn } from "@/lib/utils";

interface Props {
  ticker: string;
}

/* ─── Formatting helpers ────────────────────────────────────────────────── */

function fmtBig(v: number | null | undefined): string {
  if (v == null) return "—";
  const abs = Math.abs(v);
  const s = v < 0 ? "-" : "";
  if (abs >= 1e12) return `${s}$${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${s}$${(abs / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${s}$${(abs / 1e6).toFixed(0)}M`;
  return `${s}$${abs.toLocaleString()}`;
}

function fmtPctSurp(v: number | null | undefined): { text: string; color: string } {
  if (v == null) return { text: "—", color: "text-muted-foreground" };
  const sign = v >= 0 ? "+" : "";
  return {
    text: `${sign}${v.toFixed(2)}%`,
    color: v > 0 ? "text-green-600 dark:text-green-400" : v < 0 ? "text-red-600 dark:text-red-400" : "text-muted-foreground",
  };
}

const shortYear = (iso: string) => `FY${iso.slice(2, 4)}`;
const shortQuarter = (iso: string) => {
  const [y, m] = iso.split("-");
  return `Q${Math.ceil(parseInt(m, 10) / 3)} ${y.slice(2)}`;
};
const shortDate = (iso: string) => {
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y.slice(2)}`;
};

function yoy(curr: number | null, prev: number | null | undefined): string {
  if (curr == null || prev == null || prev === 0) return "—";
  const pct = ((curr - prev) / Math.abs(prev)) * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
}

/* ─── Chart components ──────────────────────────────────────────────────── */

interface ChartPoint {
  label: string;
  revenue?: number | null;
  revenue_est?: number | null;
  eps?: number | null;
  eps_est?: number | null;
}

function MiniTrendChart({
  data, hasEstimate,
}: { data: ChartPoint[]; hasEstimate: boolean }) {
  if (data.length === 0) {
    return <div className="text-sm text-muted-foreground text-center py-6">Nessun dato per il grafico</div>;
  }
  // Revenue is huge ($B) — scale into billions for the bar values; Y-axis label
  // says "$B". EPS stays in dollars on the right axis.
  const scaled = data.map((p) => ({
    ...p,
    revenue: p.revenue != null ? p.revenue / 1e9 : null,
    revenue_est: p.revenue_est != null ? p.revenue_est / 1e9 : null,
  }));
  // Detect EPS sign range so we draw the zero reference line only when needed
  const epsValues = scaled.flatMap((p) => [p.eps, p.eps_est]).filter((v): v is number => v != null);
  const hasNegativeEps = epsValues.some((v) => v < 0);
  const hasPositiveEps = epsValues.some((v) => v > 0);
  const showZeroLine = hasNegativeEps && hasPositiveEps;
  // EPS line: indigo so it's distinct from Revenue blue and reads well over
  // both light and dark backgrounds. The estimate line is the same hue but
  // muted + dashed.
  const EPS_COLOR = "#6366f1";       // indigo-500
  const EPS_EST_COLOR = "#a5b4fc";   // indigo-300

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart
        data={scaled}
        margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
        barCategoryGap="35%"
        barGap={2}
      >
        <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
        <XAxis dataKey="label" fontSize={10} tickLine={false} axisLine={false} />
        <YAxis
          yAxisId="rev" orientation="left" fontSize={10} tickLine={false} axisLine={false} width={36}
          tickFormatter={(v) => `${v.toFixed(0)}B`}
        />
        <YAxis
          yAxisId="eps" orientation="right" fontSize={10} tickLine={false} axisLine={false} width={36}
          tickFormatter={(v) => `$${v.toFixed(1)}`}
        />
        <Tooltip
          contentStyle={{ fontSize: 11, borderRadius: 6, padding: "4px 8px" }}
          formatter={(value: unknown, name: unknown) => {
            const n = typeof value === "number" ? value : Number(value);
            const nm = String(name ?? "");
            if (nm === "Revenue" || nm === "Revenue est") return [`$${n.toFixed(1)}B`, nm];
            if (nm === "EPS" || nm === "EPS est") return [`$${n.toFixed(2)}`, nm];
            return [String(value), nm];
          }}
        />
        <Legend wrapperStyle={{ fontSize: 10, paddingTop: 4 }} iconSize={8} />
        {showZeroLine && (
          <ReferenceLine yAxisId="eps" y={0} stroke="#64748b" strokeOpacity={0.6}
            strokeDasharray="2 2" />
        )}
        {hasEstimate && (
          <Bar yAxisId="rev" dataKey="revenue_est" name="Revenue est"
            fill="#94a3b8" fillOpacity={0.45} radius={[2, 2, 0, 0]} maxBarSize={32} />
        )}
        <Bar yAxisId="rev" dataKey="revenue" name="Revenue"
          fill="#3b82f6" radius={[2, 2, 0, 0]} maxBarSize={32} />
        {hasEstimate && (
          <Line yAxisId="eps" type="monotone" dataKey="eps_est" name="EPS est"
            stroke={EPS_EST_COLOR} strokeDasharray="4 3" strokeWidth={1.5}
            dot={{ r: 2, fill: EPS_EST_COLOR, stroke: EPS_EST_COLOR }} />
        )}
        <Line yAxisId="eps" type="monotone" dataKey="eps" name="EPS"
          stroke={EPS_COLOR} strokeWidth={2.5}
          dot={{ r: 3, fill: EPS_COLOR, stroke: EPS_COLOR }}
          activeDot={{ r: 5, fill: EPS_COLOR, stroke: "#fff", strokeWidth: 2 }} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/* ─── Quarter mapping helpers ───────────────────────────────────────────── */

/** Map an earnings RELEASE date (YYYY-MM-DD) to the fiscal quarter it
 *  reports on. Earnings are typically released ~4-6 weeks after quarter end,
 *  so we subtract 45 days to land in the right quarter. Returns "YYYY-Q[1-4]". */
function earningsDateToFiscalQuarter(isoDate: string): string {
  const d = new Date(isoDate);
  d.setDate(d.getDate() - 45);
  const y = d.getFullYear();
  const q = Math.floor(d.getMonth() / 3) + 1;
  return `${y}-Q${q}`;
}

/** Map a quarterly fiscal_quarter_end (YYYY-MM-DD) to "YYYY-Q[1-4]". */
function fiscalEndToQuarter(isoDate: string): string {
  const d = new Date(isoDate);
  const y = d.getFullYear();
  const q = Math.floor(d.getMonth() / 3) + 1;
  return `${y}-Q${q}`;
}

/* ─── Tab content builders ──────────────────────────────────────────────── */

interface AnnualEarningsAggregate {
  fiscal_year: string;
  eps_est: number | null;
  eps_real: number | null;
  surprise_pct: number | null;
  revenue_est: number | null;
  revenue_real: number | null;
}

/** Aggregate quarterly earnings into annual buckets — yfinance doesn't
 *  expose annual estimates directly, so we sum the 4 quarters of each year. */
function aggregateAnnualEarnings(
  earnings: FundamentalsEarnings[],
): Map<string, AnnualEarningsAggregate> {
  const byYear = new Map<string, AnnualEarningsAggregate>();
  for (const e of earnings) {
    const year = e.date.slice(0, 4);
    const cur = byYear.get(year) ?? {
      fiscal_year: year,
      eps_est: 0, eps_real: 0,
      surprise_pct: null,
      revenue_est: 0, revenue_real: 0,
    };
    if (e.eps_estimate != null) cur.eps_est = (cur.eps_est ?? 0) + e.eps_estimate;
    if (e.eps_reported != null) cur.eps_real = (cur.eps_real ?? 0) + e.eps_reported;
    if (e.revenue_estimate != null) cur.revenue_est = (cur.revenue_est ?? 0) + e.revenue_estimate;
    if (e.revenue_reported != null) cur.revenue_real = (cur.revenue_real ?? 0) + e.revenue_reported;
    byYear.set(year, cur);
  }
  // Compute % surprise (sum-based) per year
  for (const v of byYear.values()) {
    if (v.eps_est && v.eps_real != null) {
      v.surprise_pct = ((v.eps_real - v.eps_est) / Math.abs(v.eps_est)) * 100;
    }
  }
  return byYear;
}

function AnnualTabBody({
  annual, earnings,
}: { annual: FundamentalsAnnual[]; earnings: FundamentalsEarnings[] }) {
  const annualEarnings = useMemo(() => aggregateAnnualEarnings(earnings), [earnings]);
  const hasEstimate = Array.from(annualEarnings.values()).some((v) => v.eps_est && v.eps_est > 0);

  // Chart points: actuals from `annual`, estimates from aggregated `earnings`
  const chartData: ChartPoint[] = annual.map((a) => {
    const year = a.fiscal_year_end.slice(0, 4);
    const agg = annualEarnings.get(year);
    return {
      label: shortYear(a.fiscal_year_end),
      revenue: a.revenue,
      revenue_est: agg?.revenue_est ?? null,
      eps: a.eps,
      eps_est: agg?.eps_est ?? null,
    };
  });

  return (
    <div className="h-full flex flex-col gap-2 min-h-0">
      <div className="h-[140px] shrink-0">
        <MiniTrendChart data={chartData} hasEstimate={hasEstimate} />
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto">
        <table className="w-full text-[13px] tabular-nums">
          <thead className="text-sm text-muted-foreground uppercase sticky top-0 bg-card">
            <tr>
              <th className="px-1.5 py-1 text-left">FY</th>
              <th className="px-1.5 py-1 text-right">Rev</th>
              <th className="px-1.5 py-1 text-right">YoY</th>
              <th className="px-1.5 py-1 text-right">Net Inc</th>
              <th className="px-1.5 py-1 text-right">EPS</th>
              <th className="px-1.5 py-1 text-right">Est EPS</th>
              <th className="px-1.5 py-1 text-right">Surp</th>
            </tr>
          </thead>
          <tbody>
            {annual.map((a, i) => {
              const year = a.fiscal_year_end.slice(0, 4);
              const agg = annualEarnings.get(year);
              const surp = fmtPctSurp(agg?.surprise_pct);
              const beat = agg?.surprise_pct != null && agg.surprise_pct > 0;
              return (
                <tr key={a.fiscal_year_end} className="border-t border-border/40 hover:bg-muted/30">
                  <td className="px-1.5 py-1 font-mono">{shortYear(a.fiscal_year_end)}</td>
                  <td className="px-1.5 py-1 text-right">{fmtBig(a.revenue)}</td>
                  <td className="px-1.5 py-1 text-right text-muted-foreground">
                    {i > 0 ? yoy(a.revenue, annual[i - 1].revenue) : "—"}
                  </td>
                  <td className="px-1.5 py-1 text-right">{fmtBig(a.net_income)}</td>
                  <td className="px-1.5 py-1 text-right font-semibold">
                    {a.eps != null ? `$${a.eps.toFixed(2)}` : "—"}
                  </td>
                  <td className="px-1.5 py-1 text-right text-muted-foreground">
                    {agg?.eps_est ? `$${agg.eps_est.toFixed(2)}` : "—"}
                  </td>
                  <td className={cn("px-1.5 py-1 text-right font-semibold", surp.color)}>
                    <span className="inline-flex items-center gap-0.5 justify-end">
                      {agg?.surprise_pct != null && (beat ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />)}
                      {surp.text}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function QuarterlyTabBody({
  quarterly, earnings,
}: { quarterly: FundamentalsQuarterly[]; earnings: FundamentalsEarnings[] }) {
  // Chart points come from earnings (has est+real for both EPS and Revenue
  // when yfinance includes it) — that's the most useful trend view.
  const chartData: ChartPoint[] = useMemo(() => {
    return earnings.map((e) => ({
      label: shortDate(e.date),
      revenue: e.revenue_reported,
      revenue_est: e.revenue_estimate,
      eps: e.eps_reported,
      eps_est: e.eps_estimate,
    }));
  }, [earnings]);
  const hasEstimate = earnings.some((e) => e.eps_estimate != null);

  // Pair up earnings with quarterly history by FISCAL QUARTER (YYYY-Q1..Q4),
  // NOT by year-month. Earnings release date ≠ quarter end date — subtracting
  // ~45 days from the release date lands in the reporting quarter.
  const revByQuarter = new Map<string, number | null>();
  for (const q of quarterly) {
    revByQuarter.set(fiscalEndToQuarter(q.fiscal_quarter_end), q.revenue);
  }
  const earningsQuarters = new Set(earnings.map((e) => earningsDateToFiscalQuarter(e.date)));

  return (
    <div className="h-full flex flex-col gap-2 min-h-0">
      <div className="h-[140px] shrink-0">
        <MiniTrendChart data={chartData} hasEstimate={hasEstimate} />
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto">
        <table className="w-full text-[13px] tabular-nums">
          <thead className="text-sm text-muted-foreground uppercase sticky top-0 bg-card">
            <tr>
              <th className="px-1.5 py-1 text-left">Data</th>
              <th className="px-1.5 py-1 text-right">Rev</th>
              <th className="px-1.5 py-1 text-right">Est Rev</th>
              <th className="px-1.5 py-1 text-right">EPS</th>
              <th className="px-1.5 py-1 text-right">Est EPS</th>
              <th className="px-1.5 py-1 text-right">Surp</th>
            </tr>
          </thead>
          <tbody>
            {earnings.map((e) => {
              const surp = fmtPctSurp(e.surprise_pct);
              const beat = e.surprise_pct != null && e.surprise_pct > 0;
              const fq = earningsDateToFiscalQuarter(e.date);
              const revActual = e.revenue_reported ?? revByQuarter.get(fq) ?? null;
              return (
                <tr key={e.date} className="border-t border-border/40 hover:bg-muted/30">
                  <td className="px-1.5 py-1">
                    <span className="font-mono">{shortQuarter(`${fq.slice(0, 4)}-${(parseInt(fq.slice(6), 10) * 3).toString().padStart(2, "0")}-01`)}</span>
                    <span className="text-muted-foreground ml-1">({shortDate(e.date)})</span>
                  </td>
                  <td className="px-1.5 py-1 text-right">{fmtBig(revActual)}</td>
                  <td className="px-1.5 py-1 text-right text-muted-foreground">
                    {e.revenue_estimate != null ? fmtBig(e.revenue_estimate) : "—"}
                  </td>
                  <td className="px-1.5 py-1 text-right font-semibold">
                    {e.eps_reported != null ? `$${e.eps_reported.toFixed(2)}` : "—"}
                  </td>
                  <td className="px-1.5 py-1 text-right text-muted-foreground">
                    {e.eps_estimate != null ? `$${e.eps_estimate.toFixed(2)}` : "—"}
                  </td>
                  <td className={cn("px-1.5 py-1 text-right font-semibold", surp.color)}>
                    <span className="inline-flex items-center gap-0.5 justify-end">
                      {e.surprise_pct != null && (beat ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />)}
                      {surp.text}
                    </span>
                  </td>
                </tr>
              );
            })}
            {/* History: only quarters NOT already covered by an earnings row.
                Dedup via the YYYY-Q identifier (release date − 45d → quarter).
                Capped at 3 to avoid the table dwarfing the chart above and
                spilling visually into the next card. */}
            {quarterly
              .filter((q) => !earningsQuarters.has(fiscalEndToQuarter(q.fiscal_quarter_end)))
              .slice(0, 3)
              .map((q) => (
                <tr key={`hist-${q.fiscal_quarter_end}`} className="border-t border-border/40 text-muted-foreground italic">
                  <td className="px-1.5 py-1 font-mono">{shortQuarter(q.fiscal_quarter_end)}<span className="ml-1 text-[10px] not-italic opacity-60">(storico)</span></td>
                  <td className="px-1.5 py-1 text-right">{fmtBig(q.revenue)}</td>
                  <td className="px-1.5 py-1 text-right">—</td>
                  <td className="px-1.5 py-1 text-right">{q.eps != null ? `$${q.eps.toFixed(2)}` : "—"}</td>
                  <td className="px-1.5 py-1 text-right">—</td>
                  <td className="px-1.5 py-1 text-right">—</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ─── Outer card ────────────────────────────────────────────────────────── */

export function FundamentalsCard({ ticker }: Props) {
  const q = useStockFundamentals(ticker);

  if (q.isLoading) {
    return (
      <Card className="h-full">
        <CardContent className="p-4 h-full flex flex-col">
          <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            Fundamentals
          </div>
          <div className="flex-1 animate-pulse bg-muted/40 rounded" />
        </CardContent>
      </Card>
    );
  }

  const f = q.data;
  if (!f || f.error || (f.annual.length === 0 && f.earnings.length === 0 && f.quarterly.length === 0)) {
    return (
      <Card className="h-full">
        <CardContent className="p-4 h-full flex flex-col">
          <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            Fundamentals
          </div>
          <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground text-center px-3">
            {f?.error ? `Errore: ${f.error}` : "Dati non disponibili per questo ticker."}
          </div>
        </CardContent>
      </Card>
    );
  }

  const hasAnnual = f.annual.length > 0;
  const hasQuarterly = f.quarterly.length > 0 || f.earnings.length > 0;
  const defaultTab = hasAnnual ? "annual" : "quarterly";

  return (
    <Card className="h-full">
      <CardContent className="p-3 h-full flex flex-col min-h-0">
        <div className="flex items-center gap-2 mb-2 shrink-0">
          <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Fundamentals
          </span>
          {f.next_earnings_date && (
            <span
              className="ml-auto inline-flex items-center gap-1 text-sm px-1.5 py-0.5 rounded bg-blue-50 dark:bg-blue-950/30 border border-blue-200/60 dark:border-blue-900/40 text-blue-700 dark:text-blue-300"
              title={`Prossima earnings — EPS atteso: ${f.next_eps_estimate != null ? `$${f.next_eps_estimate.toFixed(2)}` : "—"}`}
            >
              <CalendarClock className="h-3 w-3" />
              {shortDate(f.next_earnings_date)}
              {f.next_eps_estimate != null && <> · est ${f.next_eps_estimate.toFixed(2)}</>}
            </span>
          )}
        </div>

        <Tabs defaultValue={defaultTab} className="flex-1 flex flex-col min-h-0">
          <TabsList className="h-7 p-0.5 shrink-0 self-start">
            <TabsTrigger value="annual" className="h-6 text-sm px-3" disabled={!hasAnnual}>
              Annuale
            </TabsTrigger>
            <TabsTrigger value="quarterly" className="h-6 text-sm px-3" disabled={!hasQuarterly}>
              Trimestrale
            </TabsTrigger>
          </TabsList>
          {/* `flex flex-col` on TabsContent is what stops the table from
              spilling out of the card and overlapping InsidersAnalystCard
              below — without it, h-full on the inner body has no parent
              height to measure against and the table renders at natural
              height. */}
          <TabsContent value="annual" className="m-0 mt-2 flex-1 min-h-0 flex flex-col">
            {hasAnnual ? (
              <AnnualTabBody annual={f.annual} earnings={f.earnings} />
            ) : (
              <div className="text-sm text-muted-foreground text-center py-4">N/D</div>
            )}
          </TabsContent>
          <TabsContent value="quarterly" className="m-0 mt-2 flex-1 min-h-0 flex flex-col">
            {hasQuarterly ? (
              <QuarterlyTabBody quarterly={f.quarterly} earnings={f.earnings} />
            ) : (
              <div className="text-sm text-muted-foreground text-center py-4">N/D</div>
            )}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
