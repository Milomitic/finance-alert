import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { Link } from "react-router-dom";
import { useMemo, useState } from "react";

import type { IndexBreadth } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { ACRONYM_HELP } from "@/lib/acronymHelp";
import { getIndexMeta } from "@/lib/indexMeta";
import { cn } from "@/lib/utils";

interface Props {
  data: IndexBreadth[];
}

type SortKey =
  | "code"
  | "n"
  | "total_market_cap"
  | "pct_above_sma200"
  | "pct_above_sma50"
  | "rsi_oversold_count"
  | "rsi_overbought_count"
  | "avg_change_pct"
  | "ad_ratio"
  | "new_52w_highs"
  | "new_52w_lows"
  | "volume_spikes_count";

type SortDir = "asc" | "desc" | null;

interface SortState {
  key: SortKey | null;
  dir: SortDir;
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

function fmtMarketCap(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(0)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toLocaleString()}`;
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

function getSortValue(r: IndexBreadth, key: SortKey): number | string {
  if (key === "code") return r.code;
  if (key === "ad_ratio") return r.advancers / Math.max(1, r.decliners);
  const v = r[key];
  if (v === null || v === undefined) return -Infinity;
  return v as number;
}

interface HeaderProps {
  column: SortKey;
  label: string;
  align?: "left" | "right";
  help?: string;
  state: SortState;
  onClick: (col: SortKey) => void;
}

function SortableHeader({ column, label, align = "right", help, state, onClick }: HeaderProps) {
  const active = state.key === column;
  const dir = active ? state.dir : null;
  return (
    <th className={cn("px-3 py-2", align === "left" ? "text-left" : "text-right")}>
      <button
        type="button"
        onClick={() => onClick(column)}
        title={help}
        className={cn(
          "inline-flex items-center gap-1 hover:text-foreground transition-colors",
          help && "cursor-help",
          align === "right" && "ml-auto",
        )}
      >
        <span>{label}</span>
        {dir === "desc" && <ArrowDown className="h-3 w-3 text-foreground" />}
        {dir === "asc" && <ArrowUp className="h-3 w-3 text-foreground" />}
        {!active && <ArrowUpDown className="h-3 w-3 opacity-30" />}
      </button>
    </th>
  );
}

export function BreadthMatrixTable({ data }: Props) {
  const [sort, setSort] = useState<SortState>({ key: null, dir: null });

  const handleSort = (col: SortKey) => {
    if (sort.key !== col) {
      // Default first click: descending for numbers, ascending for code
      setSort({ key: col, dir: col === "code" ? "asc" : "desc" });
    } else if (sort.dir === "desc") {
      setSort({ key: col, dir: "asc" });
    } else if (sort.dir === "asc") {
      setSort({ key: null, dir: null });
    } else {
      setSort({ key: col, dir: "desc" });
    }
  };

  const sortedData = useMemo(() => {
    if (!sort.key || !sort.dir) return data;
    const key = sort.key;
    const dir = sort.dir;
    return [...data].sort((a, b) => {
      const aVal = getSortValue(a, key);
      const bVal = getSortValue(b, key);
      if (aVal < bVal) return dir === "asc" ? -1 : 1;
      if (aVal > bVal) return dir === "asc" ? 1 : -1;
      return 0;
    });
  }, [data, sort]);

  return (
    <Card>
      <CardContent className="p-0">
        <div className="flex items-center px-4 py-2.5 bg-muted/40 border-b">
          <span className="text-sm font-semibold uppercase tracking-wide">Breadth per indice</span>
          <span className="text-sm text-muted-foreground ml-3">snapshot ultima chiusura · clicca header per ordinare</span>
        </div>
        <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
          <table className="w-full border-collapse text-sm tabular-nums">
            <thead>
              <tr className="bg-muted/30 text-xs uppercase tracking-wide text-muted-foreground">
                <SortableHeader column="code" label="Indice" align="left" state={sort} onClick={handleSort} />
                <SortableHeader column="n" label="N" help={ACRONYM_HELP.N_STOCKS} state={sort} onClick={handleSort} />
                <SortableHeader column="total_market_cap" label="Tot MC" help="Somma dei market cap noti delle stock dell'indice" state={sort} onClick={handleSort} />
                <SortableHeader column="pct_above_sma200" label=">SMA200" help={ACRONYM_HELP.SMA200} state={sort} onClick={handleSort} />
                <SortableHeader column="pct_above_sma50" label=">SMA50" help={ACRONYM_HELP.SMA50} state={sort} onClick={handleSort} />
                <SortableHeader column="rsi_oversold_count" label="RSI<30" help={ACRONYM_HELP.RSI_OVERSOLD} state={sort} onClick={handleSort} />
                <SortableHeader column="rsi_overbought_count" label="RSI>70" help={ACRONYM_HELP.RSI_OVERBOUGHT} state={sort} onClick={handleSort} />
                <SortableHeader column="avg_change_pct" label="Avg Δ%" help={ACRONYM_HELP.AVG_CHANGE} state={sort} onClick={handleSort} />
                <SortableHeader column="ad_ratio" label="A/D" help={ACRONYM_HELP.AD_RATIO} state={sort} onClick={handleSort} />
                <SortableHeader column="new_52w_highs" label="52wHi" help={ACRONYM_HELP.NEW_52W_HIGH} state={sort} onClick={handleSort} />
                <SortableHeader column="new_52w_lows" label="52wLo" help={ACRONYM_HELP.NEW_52W_LOW} state={sort} onClick={handleSort} />
                <SortableHeader column="volume_spikes_count" label="Vol×" help={ACRONYM_HELP.VOL_SPIKE} state={sort} onClick={handleSort} />
              </tr>
            </thead>
            <tbody>
              {sortedData.map((r) => (
                <tr
                  key={r.code}
                  className={cn(
                    "border-b border-border/50 hover:bg-muted/40 transition-colors",
                    rowHighlight(r),
                  )}
                  title={`${getIndexMeta(r.code).fullName} — click per filtrare browser`}
                >
                  <td className="px-4 py-2 font-semibold">
                    <Link
                      to={`/stocks?index=${encodeURIComponent(r.code)}`}
                      className="inline-flex items-center gap-2 hover:underline"
                    >
                      {getIndexMeta(r.code).countryCode && (
                        <img
                          src={`/flags/${getIndexMeta(r.code).countryCode}.svg`}
                          alt={getIndexMeta(r.code).country}
                          width={24}
                          height={16}
                          style={{ width: "24px", height: "16px", objectFit: "cover" }}
                          className="rounded-[1px] shadow-sm shrink-0"
                        />
                      )}
                      <span>{r.code}</span>
                    </Link>
                  </td>
                  <td className="text-right px-3 py-2">{r.n}</td>
                  <td className="text-right px-3 py-2 font-semibold" title={r.total_market_cap != null ? `$${r.total_market_cap.toLocaleString()}` : undefined}>
                    {fmtMarketCap(r.total_market_cap)}
                  </td>
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
