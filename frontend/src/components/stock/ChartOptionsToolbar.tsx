import { AreaChart, CandlestickChart, LineChart } from "lucide-react";

import type { ChartType } from "@/components/stock/PriceChart";
import { cn } from "@/lib/utils";

interface Props {
  chartType: ChartType;
  onChartType: (t: ChartType) => void;
  logScale: boolean;
  onLogScale: (v: boolean) => void;
}

const TYPES: { key: ChartType; label: string; Icon: typeof LineChart }[] = [
  { key: "candle", label: "Candele", Icon: CandlestickChart },
  { key: "line", label: "Linea", Icon: LineChart },
  { key: "area", label: "Area", Icon: AreaChart },
];

/** Chart render controls: candle / line / area style + linear / log scale.
 *  Segmented buttons match the RangeSelector's visual language. */
export function ChartOptionsToolbar({ chartType, onChartType, logScale, onLogScale }: Props) {
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
      <button
        type="button"
        onClick={() => onLogScale(!logScale)}
        title="Scala logaritmica"
        aria-pressed={logScale}
        className={cn(
          "h-8 px-2.5 text-sm font-medium rounded-md border transition-colors flex items-center",
          logScale
            ? "bg-background shadow-sm text-foreground border-border"
            : "bg-muted/30 text-muted-foreground hover:text-foreground",
        )}
      >
        Log
      </button>
    </div>
  );
}
