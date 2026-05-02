import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import type { Stock } from "@/api/types";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { Card, CardContent } from "@/components/ui/card";
import { useMarketSummary } from "@/hooks/useMarketSummary";
import { getStockFlagCode } from "@/lib/stockMeta";
import { cn } from "@/lib/utils";

interface Props {
  items: Stock[];
}

type SortKey = "ticker" | "name" | "exchange" | "sector" | "market_cap" | "change_pct";
type SortDir = "asc" | "desc" | null;

function fmtMc(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toLocaleString()}`;
}

interface HeaderProps {
  column: SortKey;
  label: string;
  align?: "left" | "right";
  sortKey: SortKey | null;
  sortDir: SortDir;
  onClick: (col: SortKey) => void;
}

function SortableHeader({ column, label, align = "left", sortKey, sortDir, onClick }: HeaderProps) {
  const active = sortKey === column;
  return (
    <th className={cn("px-3 py-2", align === "right" ? "text-right" : "text-left")}>
      <button
        type="button"
        onClick={() => onClick(column)}
        className={cn(
          "inline-flex items-center gap-1 hover:text-foreground transition-colors text-xs uppercase tracking-wide font-semibold",
          align === "right" && "ml-auto",
        )}
      >
        <span>{label}</span>
        {active && sortDir === "desc" && <ArrowDown className="h-3 w-3 text-foreground" />}
        {active && sortDir === "asc" && <ArrowUp className="h-3 w-3 text-foreground" />}
        {!active && <ArrowUpDown className="h-3 w-3 opacity-30" />}
      </button>
    </th>
  );
}

export function StockBrowserTable({ items }: Props) {
  const market = useMarketSummary();
  // Build a ticker -> change_pct map from snapshot's treemap data
  const changeByTicker = useMemo(() => {
    const m = new Map<string, number>();
    const treemap = market.data?.treemap ?? [];
    for (const leaf of treemap) {
      m.set(leaf.ticker, leaf.change_pct);
    }
    return m;
  }, [market.data]);

  const [sortKey, setSortKey] = useState<SortKey | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>(null);

  const handleSort = (col: SortKey) => {
    if (sortKey !== col) {
      setSortKey(col);
      setSortDir(col === "ticker" || col === "name" ? "asc" : "desc");
    } else if (sortDir === "desc") {
      setSortDir("asc");
    } else if (sortDir === "asc") {
      setSortKey(null); setSortDir(null);
    } else {
      setSortDir("desc");
    }
  };

  const sortedItems = useMemo(() => {
    if (!sortKey || !sortDir) return items;
    const dir = sortDir;
    const key = sortKey;
    return [...items].sort((a, b) => {
      let av: string | number = "";
      let bv: string | number = "";
      if (key === "change_pct") {
        av = changeByTicker.get(a.ticker) ?? -Infinity;
        bv = changeByTicker.get(b.ticker) ?? -Infinity;
      } else if (key === "market_cap") {
        av = a.market_cap ?? -Infinity;
        bv = b.market_cap ?? -Infinity;
      } else {
        av = (a[key] ?? "") as string;
        bv = (b[key] ?? "") as string;
      }
      if (av < bv) return dir === "asc" ? -1 : 1;
      if (av > bv) return dir === "asc" ? 1 : -1;
      return 0;
    });
  }, [items, sortKey, sortDir, changeByTicker]);

  if (items.length === 0) {
    return (
      <Card>
        <CardContent className="p-8 text-center text-sm text-muted-foreground">
          Nessuno stock trovato. Prova a rimuovere qualche filtro.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm tabular-nums">
            <thead className="bg-muted/30 text-muted-foreground border-b">
              <tr>
                <SortableHeader column="ticker" label="Ticker" sortKey={sortKey} sortDir={sortDir} onClick={handleSort} />
                <SortableHeader column="name" label="Nome" sortKey={sortKey} sortDir={sortDir} onClick={handleSort} />
                <SortableHeader column="exchange" label="Exchange" sortKey={sortKey} sortDir={sortDir} onClick={handleSort} />
                <SortableHeader column="sector" label="Settore" sortKey={sortKey} sortDir={sortDir} onClick={handleSort} />
                <SortableHeader column="market_cap" label="Mkt Cap" align="right" sortKey={sortKey} sortDir={sortDir} onClick={handleSort} />
                <SortableHeader column="change_pct" label="Δ%" align="right" sortKey={sortKey} sortDir={sortDir} onClick={handleSort} />
              </tr>
            </thead>
            <tbody>
              {sortedItems.map((s) => {
                const change = changeByTicker.get(s.ticker);
                const flag = getStockFlagCode(s.country);
                const changeColor = change == null
                  ? "text-muted-foreground"
                  : change > 0 ? "text-green-600 dark:text-green-400"
                  : change < 0 ? "text-red-600 dark:text-red-400"
                  : "";
                return (
                  <tr
                    key={s.id}
                    className="border-b border-border/50 hover:bg-muted/40 transition-colors"
                  >
                    <td className="px-3 py-2">
                      <Link to={`/stocks/${encodeURIComponent(s.ticker)}`} className="inline-flex items-center gap-2 font-semibold hover:underline">
                        <StockLogo ticker={s.ticker} size="xs" />
                        <span>{s.ticker}</span>
                      </Link>
                    </td>
                    <td className="px-3 py-2 text-muted-foreground truncate max-w-[280px]">
                      <Link to={`/stocks/${encodeURIComponent(s.ticker)}`} className="hover:underline">
                        {s.name}
                      </Link>
                    </td>
                    <td className="px-3 py-2">
                      <span className="inline-flex items-center gap-1.5">
                        {flag && (
                          <img
                            src={`/flags/${flag}.svg`}
                            alt={s.country ?? ""}
                            width={16} height={11}
                            style={{ width: "16px", height: "11px", objectFit: "cover" }}
                            className="rounded-[1px] shadow-sm"
                          />
                        )}
                        <span className="text-xs text-muted-foreground">{s.exchange}</span>
                      </span>
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground truncate max-w-[160px]">
                      {s.sector ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-right">{fmtMc(s.market_cap)}</td>
                    <td className={cn("px-3 py-2 text-right", changeColor)}>
                      {change == null ? "—" : `${change >= 0 ? "+" : ""}${change.toFixed(2)}%`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
