import type { IndexBreadth } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { getIndexMeta } from "@/lib/indexMeta";

interface Props {
  data: IndexBreadth[];
}

function fmtPct(v: number | null): string {
  if (v === null) return "—";
  return `${v.toFixed(0)}%`;
}

function fmtNum(v: number | null): string {
  if (v === null) return "—";
  return String(v);
}

function fmtChange(v: number | null): string {
  if (v === null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}`;
}

function rowHighlight(r: IndexBreadth): string {
  if (r.pct_above_sma200 !== null && r.pct_above_sma200 >= 70 && (r.avg_change_pct ?? 0) > 0) {
    return "bg-yellow-50/60 dark:bg-yellow-900/10";
  }
  if (r.pct_above_sma200 !== null && r.pct_above_sma200 <= 45 && (r.avg_change_pct ?? 0) < 0) {
    return "bg-red-50/60 dark:bg-red-900/10";
  }
  return "";
}

function cellTone(value: number | null, kind: "pct" | "change"): string {
  if (value === null) return "text-muted-foreground";
  if (kind === "pct") {
    if (value >= 70) return "text-green-600 dark:text-green-400 font-semibold";
    if (value <= 40) return "text-red-600 dark:text-red-400 font-semibold";
  }
  if (kind === "change") {
    if (value > 0) return "text-green-600 dark:text-green-400";
    if (value < 0) return "text-red-600 dark:text-red-400";
  }
  return "";
}

export function BreadthMatrixTable({ data }: Props) {
  return (
    <Card>
      <CardContent className="p-0">
        <div className="flex items-center px-4 py-2 bg-muted/40 border-b">
          <span className="text-xs font-semibold uppercase tracking-wide">Breadth per indice</span>
          <span className="text-xs text-muted-foreground ml-3">snapshot ultima chiusura</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-xs tabular-nums">
            <thead>
              <tr className="bg-muted/30 text-[10px] uppercase tracking-wide text-muted-foreground">
                <th className="text-left px-4 py-2">Indice</th>
                <th className="text-right px-3 py-2">N</th>
                <th className="text-right px-3 py-2">&gt;SMA200</th>
                <th className="text-right px-3 py-2">&gt;SMA50</th>
                <th className="text-right px-3 py-2">RSI&lt;30</th>
                <th className="text-right px-3 py-2">RSI&gt;70</th>
                <th className="text-right px-3 py-2">Avg Δ%</th>
                <th className="text-right px-3 py-2">A/D</th>
                <th className="text-right px-3 py-2">52wHi</th>
                <th className="text-right px-3 py-2">52wLo</th>
                <th className="text-right px-3 py-2 pr-4">Vol×</th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr
                  key={r.code}
                  className={cn(
                    "border-b border-border/50 hover:bg-muted/40 transition-colors",
                    rowHighlight(r),
                  )}
                  title={`${getIndexMeta(r.code).fullName} — drill-down disponibile in Fase 3B`}
                >
                  <td className="px-4 py-2 font-semibold">
                    <span className="inline-flex items-center gap-2">
                      {getIndexMeta(r.code).countryCode && (
                        <img
                          src={`/flags/${getIndexMeta(r.code).countryCode}.svg`}
                          alt={getIndexMeta(r.code).country}
                          style={{ height: "13px", width: "auto" }}
                          className="rounded-[1px] shadow-sm"
                        />
                      )}
                      <span>{r.code}</span>
                    </span>
                  </td>
                  <td className="text-right px-3 py-2">{r.n}</td>
                  <td className={cn("text-right px-3 py-2", cellTone(r.pct_above_sma200, "pct"))}>{fmtPct(r.pct_above_sma200)}</td>
                  <td className={cn("text-right px-3 py-2", cellTone(r.pct_above_sma50, "pct"))}>{fmtPct(r.pct_above_sma50)}</td>
                  <td className={cn("text-right px-3 py-2", r.rsi_oversold_count > 0 ? "text-amber-600" : "")}>{r.rsi_oversold_count}</td>
                  <td className={cn("text-right px-3 py-2", r.rsi_overbought_count > 0 ? "text-red-600" : "")}>{r.rsi_overbought_count}</td>
                  <td className={cn("text-right px-3 py-2", cellTone(r.avg_change_pct, "change"))}>{fmtChange(r.avg_change_pct)}</td>
                  <td className="text-right px-3 py-2">{fmtNum(r.advancers)}/{fmtNum(r.decliners)}</td>
                  <td className="text-right px-3 py-2 text-green-600 dark:text-green-400">{r.new_52w_highs}</td>
                  <td className={cn("text-right px-3 py-2", r.new_52w_lows > 0 ? "text-red-600" : "")}>{r.new_52w_lows}</td>
                  <td className="text-right px-3 py-2 pr-4">{r.volume_spikes_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
