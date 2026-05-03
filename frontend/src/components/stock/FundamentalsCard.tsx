import { ArrowDownRight, ArrowUpRight, CalendarClock } from "lucide-react";

import type {
  FundamentalsAnnual, FundamentalsEarnings, FundamentalsQuarterly,
} from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
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

function shortYear(isoDate: string): string {
  return `FY${isoDate.slice(2, 4)}`;
}

function shortQuarter(isoDate: string): string {
  // e.g. "2025-09-30" → "Q3 25" (Sept = Q3 fiscal proxy)
  const [y, m] = isoDate.split("-");
  const month = parseInt(m, 10);
  const q = Math.ceil(month / 3);
  return `Q${q} ${y.slice(2)}`;
}

function shortDate(isoDate: string): string {
  const [y, m, d] = isoDate.split("-");
  return `${d}/${m}/${y.slice(2)}`;
}

function yoy(curr: number | null, prev: number | null | undefined): string {
  if (curr == null || prev == null || prev === 0) return "—";
  const pct = ((curr - prev) / Math.abs(prev)) * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
}

function AnnualRow({ a, prev }: { a: FundamentalsAnnual; prev?: FundamentalsAnnual }) {
  return (
    <tr className="border-t border-border/40 hover:bg-muted/30">
      <td className="px-2 py-1.5 font-mono text-xs">{shortYear(a.fiscal_year_end)}</td>
      <td className="px-2 py-1.5 text-right tabular-nums">{fmtBig(a.revenue)}</td>
      <td className="px-2 py-1.5 text-right tabular-nums text-[11px] text-muted-foreground">
        {prev ? yoy(a.revenue, prev.revenue) : "—"}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums">{fmtBig(a.net_income)}</td>
      <td className="px-2 py-1.5 text-right tabular-nums">
        {a.eps != null ? `$${a.eps.toFixed(2)}` : "—"}
      </td>
    </tr>
  );
}

function QuarterRow({ q, prev }: { q: FundamentalsQuarterly; prev?: FundamentalsQuarterly }) {
  return (
    <tr className="border-t border-border/40 hover:bg-muted/30">
      <td className="px-2 py-1.5 font-mono text-xs">{shortQuarter(q.fiscal_quarter_end)}</td>
      <td className="px-2 py-1.5 text-right tabular-nums">{fmtBig(q.revenue)}</td>
      <td className="px-2 py-1.5 text-right tabular-nums text-[11px] text-muted-foreground">
        {prev ? yoy(q.revenue, prev.revenue) : "—"}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums">
        {q.eps != null ? `$${q.eps.toFixed(2)}` : "—"}
      </td>
    </tr>
  );
}

function EarningsRow({ e }: { e: FundamentalsEarnings }) {
  const surp = fmtPct(e.surprise_pct);
  const beat = e.surprise_pct != null && e.surprise_pct > 0;
  return (
    <tr className="border-t border-border/40 hover:bg-muted/30">
      <td className="px-2 py-1.5 text-xs tabular-nums">{shortDate(e.date)}</td>
      <td className="px-2 py-1.5 text-right tabular-nums text-xs text-muted-foreground">
        {e.eps_estimate != null ? `$${e.eps_estimate.toFixed(2)}` : "—"}
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums text-xs font-semibold">
        {e.eps_reported != null ? `$${e.eps_reported.toFixed(2)}` : "—"}
      </td>
      <td className={cn("px-2 py-1.5 text-right tabular-nums text-xs font-semibold", surp.color)}>
        <span className="inline-flex items-center gap-0.5 justify-end">
          {e.surprise_pct != null && (beat ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />)}
          {surp.text}
        </span>
      </td>
      <td className="px-2 py-1.5 text-right tabular-nums text-[11px] text-muted-foreground">
        {e.revenue_reported != null ? fmtBig(e.revenue_reported)
          : e.revenue_estimate != null ? `est ${fmtBig(e.revenue_estimate)}`
          : "—"}
      </td>
    </tr>
  );
}

export function FundamentalsCard({ ticker }: Props) {
  const q = useStockFundamentals(ticker);

  if (q.isLoading) {
    return (
      <Card>
        <CardContent className="p-4">
          <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            Fundamentals
          </div>
          <div className="h-32 animate-pulse bg-muted/40 rounded" />
        </CardContent>
      </Card>
    );
  }

  const f = q.data;
  if (!f || f.error || (f.annual.length === 0 && f.earnings.length === 0 && f.quarterly.length === 0)) {
    return (
      <Card>
        <CardContent className="p-4">
          <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            Fundamentals
          </div>
          <div className="text-xs text-muted-foreground">
            {f?.error ? `Errore: ${f.error}` : "Dati non disponibili per questo ticker."}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
          Fundamentals
        </div>

        {/* Next earnings forecast banner */}
        {f.next_earnings_date && (
          <div className="mb-3 px-3 py-2 rounded-md bg-blue-50 dark:bg-blue-950/30 border border-blue-200/60 dark:border-blue-900/40 flex items-center gap-2">
            <CalendarClock className="h-4 w-4 text-blue-600 dark:text-blue-400 shrink-0" />
            <div className="text-xs">
              <div className="font-semibold text-blue-700 dark:text-blue-300">
                Prossima earnings: {shortDate(f.next_earnings_date)}
              </div>
              {f.next_eps_estimate != null && (
                <div className="text-muted-foreground">
                  EPS atteso: <span className="font-mono">${f.next_eps_estimate.toFixed(2)}</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Annual income */}
        {f.annual.length > 0 && (
          <div className="mb-3">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">
              Annuali (ultimi {f.annual.length} esercizi)
            </div>
            <table className="w-full text-xs">
              <thead className="text-[10px] text-muted-foreground uppercase">
                <tr>
                  <th className="px-2 py-1 text-left">FY</th>
                  <th className="px-2 py-1 text-right">Revenue</th>
                  <th className="px-2 py-1 text-right">YoY</th>
                  <th className="px-2 py-1 text-right">Net Income</th>
                  <th className="px-2 py-1 text-right">EPS</th>
                </tr>
              </thead>
              <tbody>
                {f.annual.map((a, i) => (
                  <AnnualRow key={a.fiscal_year_end} a={a} prev={i > 0 ? f.annual[i - 1] : undefined} />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Quarterly income */}
        {f.quarterly.length > 0 && (
          <div className="mb-3">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">
              Trimestrali (ultimi {f.quarterly.length})
            </div>
            <table className="w-full text-xs">
              <thead className="text-[10px] text-muted-foreground uppercase">
                <tr>
                  <th className="px-2 py-1 text-left">Q</th>
                  <th className="px-2 py-1 text-right">Revenue</th>
                  <th className="px-2 py-1 text-right">YoY</th>
                  <th className="px-2 py-1 text-right">EPS</th>
                </tr>
              </thead>
              <tbody>
                {f.quarterly.map((q, i) => (
                  <QuarterRow key={q.fiscal_quarter_end} q={q} prev={i >= 4 ? f.quarterly[i - 4] : undefined} />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Earnings surprises */}
        {f.earnings.length > 0 && (
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-1">
              Earnings — atteso vs reported (ultimi {f.earnings.length})
            </div>
            <table className="w-full text-xs">
              <thead className="text-[10px] text-muted-foreground uppercase">
                <tr>
                  <th className="px-2 py-1 text-left">Data</th>
                  <th className="px-2 py-1 text-right">Est EPS</th>
                  <th className="px-2 py-1 text-right">Reported</th>
                  <th className="px-2 py-1 text-right">Sorpresa</th>
                  <th className="px-2 py-1 text-right">Revenue</th>
                </tr>
              </thead>
              <tbody>
                {f.earnings.map((e) => <EarningsRow key={e.date} e={e} />)}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
