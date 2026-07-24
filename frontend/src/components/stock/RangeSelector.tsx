import { cn } from "@/lib/utils";

interface Props {
  value: string;
  onChange: (range: string) => void;
}

// Renamed semantics (v2): each key now maps to a true *timeframe* —
// the bar interval the chart renders, not just a slice of trailing
// daily bars. Periods stay locked across timeframes (RSI=14, BB=20,
// EMA 20/50/200, MACD 12/26/9) so the same indicator definition
// reads differently across granularities — that's the whole point.
//
// 30m/1h are intraday (yfinance fetched live; cached 5min).
// 1d/1w/1m read from DB ohlcv_daily (resampled in-memory for w/m).
// `all` is an alias of 1d at full history.
//
// 4h was dropped per user feedback — yfinance hourly bars start at
// the trading-session open (US: 09:30, then 10:30, 11:30, ...) which
// doesn't divide cleanly into traditional 4h candle boundaries
// (00/04/08/12/16/20). Sequential 4-bar grouping produced candles
// misaligned with what other charting tools show. Use 1h for
// sub-daily granularity instead.
const OPTIONS = [
  { key: "5m",  label: "5m" },
  { key: "30m", label: "30m" },
  { key: "1h",  label: "1h" },
  { key: "1d",  label: "1d" },
  { key: "1w",  label: "1w" },
  { key: "1m",  label: "1m" },
  // "All" removed: it duplicated "1m" (same monthly bars, differing
  // only in default zoom) and cluttered the selector. Legacy ?range=all
  // links still resolve server-side → monthly.
];

export function RangeSelector({ value, onChange }: Props) {
  return (
    // max-w-full + overflow-x-auto: six timeframe buttons in an unbreakable
    // inline-flex are the widest atom in the chart toolbar. Now that the card
    // can shrink, this must scroll inside it rather than push it wide again.
    <div className="inline-flex h-8 max-w-full overflow-x-auto items-center rounded-md border bg-muted/30 p-0.5">
      {OPTIONS.map((opt) => (
        <button
          key={opt.key}
          type="button"
          onClick={() => onChange(opt.key)}
          className={cn(
            "h-7 px-3 text-sm font-medium rounded transition-colors flex items-center",
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
