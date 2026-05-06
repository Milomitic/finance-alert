import { cn } from "@/lib/utils";

interface Props {
  value: string;
  onChange: (range: string) => void;
}

// Renamed semantics (v2): each key now maps to a true *timeframe* —
// the bar interval the chart renders, not just a slice of trailing
// daily bars. Periods stay locked across timeframes (RSI=14, BB=20,
// SMA 20/50/200, MACD 12/26/9) so the same indicator definition
// reads differently across granularities — that's the whole point.
//
// 30m/1h/4h are intraday (yfinance fetched live; cached 5min).
// 1d/1w/1m read from DB ohlcv_daily (resampled in-memory for w/m).
// `all` is an alias of 1d at full history.
const OPTIONS = [
  { key: "30m", label: "30m" },
  { key: "1h",  label: "1h" },
  { key: "4h",  label: "4h" },
  { key: "1d",  label: "1d" },
  { key: "1w",  label: "1w" },
  { key: "1m",  label: "1m" },
  { key: "all", label: "All" },
];

export function RangeSelector({ value, onChange }: Props) {
  return (
    <div className="inline-flex rounded-md border bg-muted/30 p-0.5">
      {OPTIONS.map((opt) => (
        <button
          key={opt.key}
          type="button"
          onClick={() => onChange(opt.key)}
          className={cn(
            "px-3 py-1 text-sm font-medium rounded transition-colors",
            value === opt.key
              ? "bg-background shadow-sm text-foreground"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
