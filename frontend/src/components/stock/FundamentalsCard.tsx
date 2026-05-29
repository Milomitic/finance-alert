import { ArrowDownRight, ArrowUpRight, BarChart3, CalendarClock } from "lucide-react";
import { useMemo, useState } from "react";
import {
  Bar, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { stocks } from "@/api/stocks";
import type {
  FundamentalsAnnual, FundamentalsEarnings, FundamentalsQuarterly,
} from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { CardErrorOverlay } from "@/components/stock/CardErrorOverlay";
import { CardRefreshButton } from "@/components/stock/CardRefreshButton";
import { useCardRefresh } from "@/hooks/useCardRefresh";
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

/** Compare a reported value vs its estimate and return a beat/miss tone class.
 *  Returns "" when either side is missing — neutral, no coloring claim. Used
 *  to color the EPS-reported and Revenue-reported cells alongside the
 *  surprise-percent cell, so the user sees the beat/miss signal at a glance
 *  without having to read across to the rightmost column. */
function beatTone(reported: number | null | undefined, estimate: number | null | undefined): string {
  if (reported == null || estimate == null) return "";
  if (reported > estimate) return "text-green-600 dark:text-green-400";
  if (reported < estimate) return "text-red-600 dark:text-red-400";
  return "";
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

  // Chart goes oldest → newest (left → right) for readability; the table
  // below goes newest → oldest (most recent at the top) per user request.
  const annualAsc = useMemo(
    () => [...annual].sort((a, b) => a.fiscal_year_end.localeCompare(b.fiscal_year_end)),
    [annual],
  );
  const annualDesc = useMemo(() => [...annualAsc].reverse(), [annualAsc]);

  // Chart points: actuals from `annual`, estimates from aggregated `earnings`
  const chartData: ChartPoint[] = annualAsc.map((a) => {
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

  // Two stacked sections — chart with EXPLICIT pixel height (no flex/grid
  // height-calc dance), table fills remaining space and scrolls. This
  // pattern is bulletproof inside a card with `overflow-hidden` on the
  // outer Card: even if the table content is huge, scroll stays inside.
  return (
    <>
      <div style={{ height: 200 }} className="shrink-0">
        <MiniTrendChart data={chartData} hasEstimate={hasEstimate} />
      </div>
      <div className="mt-2 flex-1 min-h-0 overflow-y-auto pr-1 -mr-1">
        <table className="w-full text-[13px] tabular-nums">
          <thead className="text-sm text-muted-foreground uppercase sticky top-0 bg-card z-10">
            <tr>
              <th className="px-1.5 py-1 text-left">FY</th>
              <th className="px-1.5 py-1 text-right">Rev</th>
              <th className="px-1.5 py-1 text-right">YoY</th>
              <th className="px-1.5 py-1 text-right">Net Inc</th>
              <th
                className="px-1.5 py-1 text-right"
                title="EPS GAAP (conto economico) — include poste straordinarie (es. costi di fusione, impairment). Può divergere fortemente dalla somma degli EPS adjusted trimestrali."
              >
                EPS<span className="ml-0.5 text-[9px] align-top text-muted-foreground">GAAP</span>
              </th>
              <th
                className="px-1.5 py-1 text-right"
                title="EPS adjusted — somma degli EPS reported trimestrali (esclude le poste straordinarie). È la metrica confrontata col consensus analisti (Est EPS) e usata per la Surprise."
              >
                EPS adj.
              </th>
              <th className="px-1.5 py-1 text-right">Est EPS</th>
              <th className="px-1.5 py-1 text-right">Surp</th>
            </tr>
          </thead>
          <tbody>
            {annualDesc.map((a) => {
              const year = a.fiscal_year_end.slice(0, 4);
              const agg = annualEarnings.get(year);
              const surp = fmtPctSurp(agg?.surprise_pct);
              const beat = agg?.surprise_pct != null && agg.surprise_pct > 0;
              // YoY: compare against the year before (one position earlier
              // in the ASC array, since DESC walks newest → oldest).
              const ascIdx = annualAsc.findIndex((x) => x.fiscal_year_end === a.fiscal_year_end);
              const prevYear = ascIdx > 0 ? annualAsc[ascIdx - 1] : null;
              // Adjusted annual EPS = Σ quarterly reported EPS. This is
              // the consensus-comparable figure (Est EPS / Surp are
              // adjusted-based), so colour the BEAT/MISS on it — not on
              // GAAP, where comparing to an adjusted estimate is
              // apples-to-oranges (the OMC FY25 −0.27 vs 8.25 case).
              const epsAdj = agg?.eps_real ?? null;
              const epsAdjTone = beatTone(epsAdj, agg?.eps_est);
              return (
                <tr key={a.fiscal_year_end} className="border-t border-border/40 hover:bg-muted/30">
                  <td className="px-1.5 py-1 font-mono">{shortYear(a.fiscal_year_end)}</td>
                  <td className="px-1.5 py-1 text-right">{fmtBig(a.revenue)}</td>
                  <td className="px-1.5 py-1 text-right text-muted-foreground">
                    {prevYear ? yoy(a.revenue, prevYear.revenue) : "—"}
                  </td>
                  <td className="px-1.5 py-1 text-right">{fmtBig(a.net_income)}</td>
                  {/* GAAP EPS — neutral/muted: it's the audited legal
                      figure but NOT comparable to the adjusted consensus,
                      so no beat/miss colour claim here. */}
                  <td className="px-1.5 py-1 text-right text-muted-foreground">
                    {a.eps != null ? `$${a.eps.toFixed(2)}` : "—"}
                  </td>
                  <td className={cn("px-1.5 py-1 text-right font-semibold", epsAdjTone)}>
                    {epsAdj != null ? `$${epsAdj.toFixed(2)}` : "—"}
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
    </>
  );
}

function QuarterlyTabBody({
  quarterly, earnings, nextEarningsDate, nextEarningsWhen, nextEpsEstimate, nextRevenueEstimate,
}: {
  quarterly: FundamentalsQuarterly[];
  earnings: FundamentalsEarnings[];
  nextEarningsDate: string | null;
  /** Pre/after-market hint for the upcoming earnings — drives sun/moon glyph. */
  nextEarningsWhen: "pre" | "after" | null;
  nextEpsEstimate: number | null;
  nextRevenueEstimate: number | null;
}) {
  // **Dedup earnings by fiscal quarter**, keeping the most recent release per
  // quarter. yfinance occasionally returns two earnings entries that both map
  // to the same fiscal quarter via the `release_date - 45d` heuristic — for
  // example a fiscal-Q1 release in early Feb and an estimates row carrying
  // the next quarter's estimates that lands in the same bucket. The user
  // sees both as "Q1 26" with different dates which is confusing. We pick
  // the row with the latest release date (which is also the row with
  // populated `eps_reported` 99% of the time) and drop the rest.
  const earningsDedup = useMemo(() => {
    const byFq = new Map<string, FundamentalsEarnings>();
    for (const e of earnings) {
      const fq = earningsDateToFiscalQuarter(e.date);
      const existing = byFq.get(fq);
      if (!existing || e.date.localeCompare(existing.date) > 0) {
        byFq.set(fq, e);
      }
    }
    return Array.from(byFq.values());
  }, [earnings]);

  // Chart goes oldest → newest (left → right) so the trend reads naturally.
  // The table below reverses to show newest → oldest at the top. Both views
  // operate on the deduped set.
  const earningsAsc = useMemo(
    () => [...earningsDedup].sort((a, b) => a.date.localeCompare(b.date)),
    [earningsDedup],
  );
  const earningsDesc = useMemo(() => [...earningsAsc].reverse(), [earningsAsc]);

  const chartData: ChartPoint[] = useMemo(() => {
    return earningsAsc.map((e) => ({
      label: shortDate(e.date),
      revenue: e.revenue_reported,
      revenue_est: e.revenue_estimate,
      eps: e.eps_reported,
      eps_est: e.eps_estimate,
    }));
  }, [earningsAsc]);
  const hasEstimate = earningsDedup.some((e) => e.eps_estimate != null);

  // Pair up earnings with quarterly history by FISCAL QUARTER (YYYY-Q1..Q4),
  // NOT by year-month. Earnings release date ≠ quarter end date — subtracting
  // ~45 days from the release date lands in the reporting quarter.
  const revByQuarter = new Map<string, number | null>();
  // GAAP quarterly EPS (from the income statement) keyed by fiscal
  // quarter, so each earnings row can show GAAP alongside the adjusted
  // `eps_reported`. This is what makes the OMC story legible at the
  // quarter level: Q4'25 GAAP −4.02 next to adj. +2.59.
  const epsGaapByQuarter = new Map<string, number | null>();
  for (const q of quarterly) {
    revByQuarter.set(fiscalEndToQuarter(q.fiscal_quarter_end), q.revenue);
    epsGaapByQuarter.set(fiscalEndToQuarter(q.fiscal_quarter_end), q.eps);
  }
  // NOTE: the "storico" tail (quarters from `quarterly` not covered by
  // `earnings`) was removed per user request. Those rows were redundant —
  // they carried only revenue/EPS without estimates or surprise %, and
  // visually duplicated quarter labels already shown above. The deduped
  // earnings list is the canonical view.

  // Next-earnings row only renders when we have at least a date — without
  // a date the whole row is meaningless. EPS/Revenue estimates may be null
  // (yfinance hasn't published consensus yet) and we render "—" in that case.
  const hasNextRow = !!nextEarningsDate;

  return (
    <>
      <div style={{ height: 200 }} className="shrink-0">
        <MiniTrendChart data={chartData} hasEstimate={hasEstimate} />
      </div>
      <div className="mt-2 flex-1 min-h-0 overflow-y-auto pr-1 -mr-1">
        <table className="w-full text-[13px] tabular-nums">
          <thead className="text-sm text-muted-foreground uppercase sticky top-0 bg-card z-10">
            <tr>
              <th className="px-1.5 py-1 text-left">Data</th>
              <th className="px-1.5 py-1 text-right">Rev</th>
              <th className="px-1.5 py-1 text-right">Est Rev</th>
              <th
                className="px-1.5 py-1 text-right"
                title="EPS GAAP del trimestre (conto economico) — include poste straordinarie (es. costi di fusione, impairment)."
              >
                EPS<span className="ml-0.5 text-[9px] align-top text-muted-foreground">GAAP</span>
              </th>
              <th
                className="px-1.5 py-1 text-right"
                title="EPS adjusted reported — la cifra confrontata col consensus (Est EPS) e usata per la Surprise."
              >
                EPS adj.
              </th>
              <th className="px-1.5 py-1 text-right">Est EPS</th>
              <th className="px-1.5 py-1 text-right">Surp</th>
            </tr>
          </thead>
          <tbody>
            {/* Forward-looking row: next earnings event. Date + estimates are
                the only populated cells (no actuals yet — that's the point).
                Subtle blue tint + italic to set it apart from confirmed rows. */}
            {hasNextRow && (
              <tr className="border-t border-border/40 bg-blue-50/60 dark:bg-blue-950/20">
                <td className="px-1.5 py-1">
                  <span className="inline-flex items-center gap-1 font-mono text-blue-700 dark:text-blue-300">
                    {shortDate(nextEarningsDate!)}
                  </span>
                  {/* Pre/after-market icon — same glyphs as the calendar's
                      EventChip. Sun = pre-open release, moon = after-close. */}
                  {nextEarningsWhen === "pre" && (
                    <span
                      className="ml-1 text-[11px] leading-none shrink-0 text-amber-500"
                      title="Pre-market: earnings rilasciati prima dell'apertura della sessione"
                      aria-label="pre-market"
                    >
                      ☀
                    </span>
                  )}
                  {nextEarningsWhen === "after" && (
                    <span
                      className="ml-1 text-[11px] leading-none shrink-0 opacity-80"
                      title="After-market: earnings rilasciati dopo la chiusura della sessione"
                      aria-label="after-market"
                    >
                      ☾
                    </span>
                  )}
                  <span className="ml-1 text-[10px] uppercase tracking-wider text-blue-700/80 dark:text-blue-300/80 font-semibold">
                    prossima
                  </span>
                </td>
                <td className="px-1.5 py-1 text-right text-muted-foreground italic">—</td>
                <td className="px-1.5 py-1 text-right text-blue-700 dark:text-blue-300 font-semibold">
                  {nextRevenueEstimate != null ? fmtBig(nextRevenueEstimate) : "—"}
                </td>
                {/* GAAP EPS + adj. EPS — both empty (no actuals yet). */}
                <td className="px-1.5 py-1 text-right text-muted-foreground italic">—</td>
                <td className="px-1.5 py-1 text-right text-muted-foreground italic">—</td>
                <td className="px-1.5 py-1 text-right text-blue-700 dark:text-blue-300 font-semibold">
                  {nextEpsEstimate != null ? `$${nextEpsEstimate.toFixed(2)}` : "—"}
                </td>
                <td className="px-1.5 py-1 text-right text-muted-foreground italic">—</td>
              </tr>
            )}
            {earningsDesc.map((e) => {
              const surp = fmtPctSurp(e.surprise_pct);
              const beat = e.surprise_pct != null && e.surprise_pct > 0;
              const fq = earningsDateToFiscalQuarter(e.date);
              const revActual = e.revenue_reported ?? revByQuarter.get(fq) ?? null;
              const revTone = beatTone(revActual, e.revenue_estimate);
              const epsTone = beatTone(e.eps_reported, e.eps_estimate);
              return (
                <tr key={e.date} className="border-t border-border/40 hover:bg-muted/30">
                  <td className="px-1.5 py-1">
                    <span className="font-mono">{shortQuarter(`${fq.slice(0, 4)}-${(parseInt(fq.slice(6), 10) * 3).toString().padStart(2, "0")}-01`)}</span>
                    <span className="text-muted-foreground ml-1">({shortDate(e.date)})</span>
                  </td>
                  <td className={cn("px-1.5 py-1 text-right font-semibold", revTone)}>
                    {fmtBig(revActual)}
                  </td>
                  <td className="px-1.5 py-1 text-right text-muted-foreground">
                    {e.revenue_estimate != null ? fmtBig(e.revenue_estimate) : "—"}
                  </td>
                  {/* GAAP EPS for the quarter (from the income
                      statement) — muted, no beat/miss claim (not
                      consensus-comparable). "—" when yfinance has no
                      quarterly statement row for this fiscal quarter. */}
                  <td className="px-1.5 py-1 text-right text-muted-foreground">
                    {(() => {
                      const g = epsGaapByQuarter.get(fq);
                      return g != null ? `$${g.toFixed(2)}` : "—";
                    })()}
                  </td>
                  <td className={cn("px-1.5 py-1 text-right font-semibold", epsTone)}>
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
          </tbody>
        </table>
      </div>
    </>
  );
}

/* ─── Outer card ────────────────────────────────────────────────────────── */

type TabKey = "annual" | "quarterly";

export function FundamentalsCard({ ticker }: Props) {
  const q = useStockFundamentals(ticker);
  const { refresh, isRefreshing, refreshError } = useCardRefresh({
    queryKey: ["stocks", ticker, "fundamentals"],
    mutationFn: () => stocks.fundamentals(ticker, { force: true }),
  });
  // Default tab is now "quarterly" — the user reads quarterly results more
  // frequently than annual (earnings season cadence is the dominant info
  // flow), and the upcoming-earnings forecast row only renders here.
  const [tab, setTab] = useState<TabKey>("quarterly");

  if (q.isLoading) {
    return (
      <Card className="h-full overflow-hidden">
        <CardContent className="p-4 h-full flex flex-col">
          <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            Fundamentals
          </div>
          {/* Reserve enough height (chart 200 + table ~250) so the layout
              doesn't jump when data lands. */}
          <div className="h-[450px] animate-pulse bg-muted/40 rounded" />
        </CardContent>
      </Card>
    );
  }

  const f = q.data;
  if (!f || f.error || (f.annual.length === 0 && f.earnings.length === 0 && f.quarterly.length === 0)) {
    return (
      <Card className="h-full overflow-hidden">
        <CardContent className="p-4 h-full flex flex-col">
          <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            Fundamentals
          </div>
          <div className="py-12 flex items-center justify-center text-sm text-muted-foreground text-center px-3">
            {f?.error ? `Errore: ${f.error}` : "Dati non disponibili per questo ticker."}
          </div>
        </CardContent>
      </Card>
    );
  }

  const hasAnnual = f.annual.length > 0;
  const hasQuarterly = f.quarterly.length > 0 || f.earnings.length > 0;
  // Effective tab — fall back if user-selected tab has no data
  const effective: TabKey =
    tab === "annual" && !hasAnnual ? "quarterly" :
    tab === "quarterly" && !hasQuarterly ? "annual" :
    tab;

  /*
   * Layout chain — designed to make overflow IMPOSSIBLE:
   *
   *   Card (h-full + overflow-hidden)        ← clips anything outside 400px
   *     CardContent (h-full flex flex-col)
   *       Header (shrink-0)                  ← natural height, won't grow
   *       Tab strip (shrink-0)               ← natural height
   *       Body container (flex-1 min-h-0)    ← takes the rest, can shrink
   *         Chart (style.height = 150px)     ← explicit pixel height
   *         Table div (flex-1 min-h-0 overflow-y-auto)  ← scrolls
   *
   * Key wins vs the previous attempt:
   *   1. `overflow-hidden` on Card — no escape regardless of inner bugs.
   *   2. Native useState instead of Radix Tabs — no display:none / data-state
   *      games that conflict with our flex chain.
   *   3. Chart uses inline `style={{ height: 150 }}` — Recharts always sees
   *      a concrete pixel value, no flex-track height calculation needed.
   *   4. `flex-1 min-h-0 overflow-y-auto` on the table div is the ONE place
   *      overflow can happen — and it's contained.
   */

  // h-full so the card fills the grid row (height set by `items-stretch` to
  // match the tallest sibling). Chart is a fixed 200px and the data table
  // renders ALL rows inline — per user constraint, Fundamentals never scrolls
  // its tables. That makes Fundamentals the *natural floor* for the row
  // height: News + Valuation cards scroll internally if they have more
  // content than this floor allows.
  // `overflow-hidden` stays as a safety net so any rogue extra-wide row
  // clips at the card edge instead of overflowing into siblings.
  return (
    <Card className="h-full overflow-hidden">
      <CardContent className="p-3 h-full flex flex-col">
        {/* Header */}
        <SectionTitle
          icon={BarChart3}
          label="Fundamentals"
          className="mb-2 shrink-0"
          right={
            <div className="flex items-center gap-2">
              {f.next_earnings_date ? (
                <span
                  className="inline-flex items-center gap-1 text-sm px-1.5 py-0.5 rounded bg-blue-50 dark:bg-blue-950/30 border border-blue-200/60 dark:border-blue-900/40 text-blue-700 dark:text-blue-300"
                  title={`Prossima earnings — EPS atteso: ${f.next_eps_estimate != null ? `$${f.next_eps_estimate.toFixed(2)}` : "—"}`}
                >
                  <CalendarClock className="h-3 w-3" />
                  {shortDate(f.next_earnings_date)}
                  {f.next_eps_estimate != null && <> · est ${f.next_eps_estimate.toFixed(2)}</>}
                </span>
              ) : null}
              <CardRefreshButton
                onClick={refresh}
                busy={isRefreshing}
                title="Aggiorna fundamentals"
              />
            </div>
          }
        />

        {refreshError ? (
          <CardErrorOverlay
            error={refreshError}
            onRetry={refresh}
            retrying={isRefreshing}
          />
        ) : (
          <>
            {/* Tab strip — plain buttons, no Radix */}
            <div className="inline-flex items-center gap-1 mb-2 shrink-0 self-start rounded-md bg-muted/50 p-0.5">
              {([
                { key: "annual" as const, label: "Annuale", enabled: hasAnnual },
                { key: "quarterly" as const, label: "Trimestrale", enabled: hasQuarterly },
              ]).map((t) => (
                <button
                  key={t.key}
                  type="button"
                  disabled={!t.enabled}
                  onClick={() => setTab(t.key)}
                  className={cn(
                    "h-6 px-3 text-sm rounded font-medium transition-colors",
                    effective === t.key
                      ? "bg-background shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                    !t.enabled && "opacity-40 cursor-not-allowed",
                  )}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {/* Body — chart (fixed 200px shrink-0) + table fills remaining row
                space and scrolls internally. Required because the parent grid
                now caps the row at `lg:h-[640px]` (StockDetailPage); without
                this chain the table would overflow the card's bottom edge. */}
            <div className="flex-1 min-h-0 flex flex-col">
              {effective === "annual" && hasAnnual && (
                <AnnualTabBody annual={f.annual} earnings={f.earnings} />
              )}
              {effective === "quarterly" && hasQuarterly && (
                <QuarterlyTabBody
                  quarterly={f.quarterly}
                  earnings={f.earnings}
                  nextEarningsDate={f.next_earnings_date}
                  nextEarningsWhen={f.next_earnings_when ?? null}
                  nextEpsEstimate={f.next_eps_estimate}
                  nextRevenueEstimate={f.next_revenue_estimate}
                />
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
