import type { IndexBreadth } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

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
        <div className="flex items-center px-3 py-1.5 bg-muted/40 border-b">
          <span className="text-[11px] font-semibold">Breadth per indice</span>
          <span className="text-[10px] text-muted-foreground ml-2">snapshot ultima chiusura</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[11px] tabular-nums">
            <thead>
              <tr className="bg-muted/30 text-[9px] uppercase text-muted-foreground">
                <th className="text-left px-3 py-1">Indice</th>
                <th className="text-right px-2 py-1">N</th>
                <th className="text-right px-2 py-1">&gt;SMA200</th>
                <th className="text-right px-2 py-1">&gt;SMA50</th>
                <th className="text-right px-2 py-1">RSI&lt;30</th>
                <th className="text-right px-2 py-1">RSI&gt;70</th>
                <th className="text-right px-2 py-1">Avg Δ%</th>
                <th className="text-right px-2 py-1">A/D</th>
                <th className="text-right px-2 py-1">52wHi</th>
                <th className="text-right px-2 py-1">52wLo</th>
                <th className="text-right px-2 py-1 pr-3">Vol×</th>
              </tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr
                  key={r.code}
                  className={cn("border-b border-border/50", rowHighlight(r))}
                  title="Drill-down disponibile in Fase 3B"
                >
                  <td className="px-3 py-1 font-semibold">{r.code}</td>
                  <td className="text-right px-2 py-1">{r.n}</td>
                  <td className={cn("text-right px-2 py-1", cellTone(r.pct_above_sma200, "pct"))}>{fmtPct(r.pct_above_sma200)}</td>
                  <td className={cn("text-right px-2 py-1", cellTone(r.pct_above_sma50, "pct"))}>{fmtPct(r.pct_above_sma50)}</td>
                  <td className={cn("text-right px-2 py-1", r.rsi_oversold_count > 0 ? "text-amber-600" : "")}>{r.rsi_oversold_count}</td>
                  <td className={cn("text-right px-2 py-1", r.rsi_overbought_count > 0 ? "text-red-600" : "")}>{r.rsi_overbought_count}</td>
                  <td className={cn("text-right px-2 py-1", cellTone(r.avg_change_pct, "change"))}>{fmtChange(r.avg_change_pct)}</td>
                  <td className="text-right px-2 py-1">{fmtNum(r.advancers)}/{fmtNum(r.decliners)}</td>
                  <td className="text-right px-2 py-1 text-green-600 dark:text-green-400">{r.new_52w_highs}</td>
                  <td className={cn("text-right px-2 py-1", r.new_52w_lows > 0 ? "text-red-600" : "")}>{r.new_52w_lows}</td>
                  <td className="text-right px-2 py-1 pr-3">{r.volume_spikes_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
