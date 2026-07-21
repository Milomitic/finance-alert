import { AreaChart, CandlestickChart, Download, LineChart, X } from "lucide-react";
import { useEffect, useState } from "react";

import type { ChartType } from "@/components/stock/PriceChart";
import { cn } from "@/lib/utils";

/** Curated benchmark indices (subset of the dashboard's LIVE_ASSET_DEFINITIONS)
 *  fetched via /api/markets/{symbol}/detail. "" = no overlay. */
export const BENCHMARKS: { symbol: string; label: string }[] = [
  { symbol: "", label: "Benchmark…" },
  { symbol: "^GSPC", label: "S&P 500" },
  { symbol: "^IXIC", label: "Nasdaq" },
  { symbol: "^STOXX50E", label: "Euro Stoxx 50" },
  { symbol: "FTSEMIB.MI", label: "FTSE MIB" },
];

interface Props {
  chartType: ChartType;
  onChartType: (t: ChartType) => void;
  benchmark: string;
  onBenchmark: (symbol: string) => void;
  compareTicker: string;
  onCompareTicker: (ticker: string) => void;
  onExport: () => void;
}

const TYPES: { key: ChartType; label: string; Icon: typeof LineChart }[] = [
  { key: "candle", label: "Candele", Icon: CandlestickChart },
  { key: "line", label: "Linea", Icon: LineChart },
  { key: "area", label: "Area", Icon: AreaChart },
];

/** Chart render controls: candle / line / area style, a benchmark overlay
 *  picker, and PNG export. Segmented buttons match the RangeSelector's visual
 *  language. */
export function ChartOptionsToolbar({
  chartType, onChartType, benchmark, onBenchmark, compareTicker, onCompareTicker, onExport,
}: Props) {
  // Local input state; commit the compare ticker on Enter / blur so we don't
  // fire a fetch on every keystroke.
  const [cmp, setCmp] = useState(compareTicker);
  useEffect(() => setCmp(compareTicker), [compareTicker]);
  const commit = () => onCompareTicker(cmp.trim().toUpperCase());

  return (
    <div className="inline-flex items-center gap-1.5">
      <div className="inline-flex h-8 items-center rounded-md border bg-muted/30 p-0.5">
        {TYPES.map(({ key, label, Icon }) => (
          <button
            key={key}
            type="button"
            onClick={() => onChartType(key)}
            title={label}
            aria-label={label}
            aria-pressed={chartType === key}
            className={cn(
              "h-7 px-2 rounded transition-colors flex items-center",
              chartType === key
                ? "bg-background shadow-sm text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Icon className="h-4 w-4" />
          </button>
        ))}
      </div>
      <select
        value={benchmark}
        onChange={(e) => onBenchmark(e.target.value)}
        title="Confronta con un indice"
        aria-label="Benchmark"
        className={cn(
          "h-8 px-2 text-sm font-medium rounded-md border bg-muted/30 cursor-pointer",
          "transition-colors hover:text-foreground",
          benchmark ? "text-foreground" : "text-muted-foreground",
        )}
      >
        {BENCHMARKS.map((b) => (
          <option key={b.symbol} value={b.symbol}>
            {b.label}
          </option>
        ))}
      </select>
      {/* Multi-ticker compare — type a ticker, commit on Enter/blur. */}
      <div className="relative inline-flex items-center">
        <input
          value={cmp}
          onChange={(e) => setCmp(e.target.value.toUpperCase())}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
          }}
          onBlur={commit}
          placeholder="vs ticker…"
          aria-label="Confronta con un titolo"
          title="Sovrapponi un altro titolo (ribasato)"
          className={cn(
            "h-8 w-24 px-2 text-sm rounded-md border bg-muted/30",
            compareTicker ? "pr-6 text-foreground" : "text-muted-foreground",
          )}
        />
        {compareTicker && (
          <button
            type="button"
            onClick={() => {
              setCmp("");
              onCompareTicker("");
            }}
            title="Rimuovi confronto"
            aria-label="Rimuovi confronto"
            className="absolute right-1 text-muted-foreground hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
      <button
        type="button"
        onClick={onExport}
        title="Esporta PNG"
        aria-label="Esporta PNG"
        className="h-8 w-8 rounded-md border bg-muted/30 text-muted-foreground hover:text-foreground transition-colors flex items-center justify-center"
      >
        <Download className="h-4 w-4" />
      </button>
    </div>
  );
}
