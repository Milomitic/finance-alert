import { ArrowDownRight, ArrowUpRight, CalendarClock } from "lucide-react";

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

function fmtBig(v: number | null | undefined, currency: string = "$"): string {
  if (v == null) return "—";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1e12) return `${sign}${currency}${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${sign}${currency}${(abs / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${sign}${currency}${(abs / 1e6).toFixed(0)}M`;
  return `${sign}${currency}${abs.toLocaleString()}`;
}

function fmtPct(v: number | null | undefined): { text: string; color: string } {
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

/* Compact tables: tighter padding (px-1.5 py-1), text-[11px] base, no box
   borders between rows — just hover highlight. Scroll inside the tab body
   keeps the card height fixed. */

function AnnualTable({ rows }: { rows: FundamentalsAnnual[] }) {
  return (
    <table className="w-full text-[11px] tabular-nums">
      <thead className="text-[10px] text-muted-foreground uppercase">
        <tr>
          <th className="px-1.5 py-1 text-left">FY</th>
          <th className="px-1.5 py-1 text-right">Rev</th>
          <th className="px-1.5 py-1 text-right">YoY</th>
          <th className="px-1.5 py-1 text-right">Net Inc</th>
          <th className="px-1.5 py-1 text-right">EPS</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((a, i) => (
          <tr key={a.fiscal_year_end} className="border-t border-border/40 hover:bg-muted/30">
            <td className="px-1.5 py-1 font-mono">{shortYear(a.fiscal_year_end)}</td>
            <td className="px-1.5 py-1 text-right">{fmtBig(a.revenue)}</td>
            <td className="px-1.5 py-1 text-right text-muted-foreground">
              {i > 0 ? yoy(a.revenue, rows[i - 1].revenue) : "—"}
            </td>
            <td className="px-1.5 py-1 text-right">{fmtBig(a.net_income)}</td>
            <td className="px-1.5 py-1 text-right">{a.eps != null ? `$${a.eps.toFixed(2)}` : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function QuarterlyTable({ rows }: { rows: FundamentalsQuarterly[] }) {
  return (
    <table className="w-full text-[11px] tabular-nums">
      <thead className="text-[10px] text-muted-foreground uppercase">
        <tr>
          <th className="px-1.5 py-1 text-left">Q</th>
          <th className="px-1.5 py-1 text-right">Rev</th>
          <th className="px-1.5 py-1 text-right">YoY</th>
          <th className="px-1.5 py-1 text-right">EPS</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((q, i) => (
          <tr key={q.fiscal_quarter_end} className="border-t border-border/40 hover:bg-muted/30">
            <td className="px-1.5 py-1 font-mono">{shortQuarter(q.fiscal_quarter_end)}</td>
            <td className="px-1.5 py-1 text-right">{fmtBig(q.revenue)}</td>
            <td className="px-1.5 py-1 text-right text-muted-foreground">
              {i >= 4 ? yoy(q.revenue, rows[i - 4].revenue) : "—"}
            </td>
            <td className="px-1.5 py-1 text-right">{q.eps != null ? `$${q.eps.toFixed(2)}` : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function EarningsTable({ rows }: { rows: FundamentalsEarnings[] }) {
  return (
    <table className="w-full text-[11px] tabular-nums">
      <thead className="text-[10px] text-muted-foreground uppercase">
        <tr>
          <th className="px-1.5 py-1 text-left">Data</th>
          <th className="px-1.5 py-1 text-right">Est</th>
          <th className="px-1.5 py-1 text-right">Real</th>
          <th className="px-1.5 py-1 text-right">Surp</th>
          <th className="px-1.5 py-1 text-right">Rev</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((e) => {
          const surp = fmtPct(e.surprise_pct);
          const beat = e.surprise_pct != null && e.surprise_pct > 0;
          return (
            <tr key={e.date} className="border-t border-border/40 hover:bg-muted/30">
              <td className="px-1.5 py-1">{shortDate(e.date)}</td>
              <td className="px-1.5 py-1 text-right text-muted-foreground">
                {e.eps_estimate != null ? `$${e.eps_estimate.toFixed(2)}` : "—"}
              </td>
              <td className="px-1.5 py-1 text-right font-semibold">
                {e.eps_reported != null ? `$${e.eps_reported.toFixed(2)}` : "—"}
              </td>
              <td className={cn("px-1.5 py-1 text-right font-semibold", surp.color)}>
                <span className="inline-flex items-center gap-0.5 justify-end">
                  {e.surprise_pct != null && (beat ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />)}
                  {surp.text}
                </span>
              </td>
              <td className="px-1.5 py-1 text-right text-[10px] text-muted-foreground">
                {e.revenue_reported != null ? fmtBig(e.revenue_reported)
                  : e.revenue_estimate != null ? `est ${fmtBig(e.revenue_estimate)}`
                  : "—"}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

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
          <div className="flex-1 flex items-center justify-center text-xs text-muted-foreground text-center px-3">
            {f?.error ? `Errore: ${f.error}` : "Dati non disponibili per questo ticker."}
          </div>
        </CardContent>
      </Card>
    );
  }

  // Pick the best default tab based on what data is available
  const defaultTab =
    f.annual.length > 0 ? "annual" :
    f.quarterly.length > 0 ? "quarterly" :
    "earnings";

  return (
    <Card className="h-full">
      <CardContent className="p-4 h-full flex flex-col min-h-0">
        <div className="flex items-center gap-2 mb-2 shrink-0">
          <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Fundamentals
          </span>
          {f.next_earnings_date && (
            <span
              className="ml-auto inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-blue-50 dark:bg-blue-950/30 border border-blue-200/60 dark:border-blue-900/40 text-blue-700 dark:text-blue-300"
              title={`Prossima earnings — EPS atteso: ${f.next_eps_estimate != null ? `$${f.next_eps_estimate.toFixed(2)}` : "—"}`}
            >
              <CalendarClock className="h-3 w-3" />
              {shortDate(f.next_earnings_date)}
              {f.next_eps_estimate != null && <> · est ${f.next_eps_estimate.toFixed(2)}</>}
            </span>
          )}
        </div>

        <Tabs defaultValue={defaultTab} className="flex-1 flex flex-col min-h-0">
          <TabsList className="h-7 p-0.5 shrink-0">
            <TabsTrigger value="annual" className="h-6 text-[10px] px-2" disabled={f.annual.length === 0}>
              Annuali
            </TabsTrigger>
            <TabsTrigger value="quarterly" className="h-6 text-[10px] px-2" disabled={f.quarterly.length === 0}>
              Trimestrali
            </TabsTrigger>
            <TabsTrigger value="earnings" className="h-6 text-[10px] px-2" disabled={f.earnings.length === 0}>
              Earnings
            </TabsTrigger>
          </TabsList>
          <TabsContent value="annual" className="m-0 mt-2 flex-1 min-h-0 overflow-y-auto">
            {f.annual.length > 0 ? <AnnualTable rows={f.annual} /> :
              <div className="text-xs text-muted-foreground text-center py-4">N/D</div>}
          </TabsContent>
          <TabsContent value="quarterly" className="m-0 mt-2 flex-1 min-h-0 overflow-y-auto">
            {f.quarterly.length > 0 ? <QuarterlyTable rows={f.quarterly} /> :
              <div className="text-xs text-muted-foreground text-center py-4">N/D</div>}
          </TabsContent>
          <TabsContent value="earnings" className="m-0 mt-2 flex-1 min-h-0 overflow-y-auto">
            {f.earnings.length > 0 ? <EarningsTable rows={f.earnings} /> :
              <div className="text-xs text-muted-foreground text-center py-4">N/D</div>}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
