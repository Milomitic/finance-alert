import { useMemo, useState } from "react";
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import type { IndexBreadth, RsiDistribution } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface Props {
  rsi: RsiDistribution;
  indices: IndexBreadth[];
}

const BIN_LABELS = ["0-10", "10-20", "20-30", "30-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"];

const COLORS: Record<string, string> = {
  SP500:   "#3b82f6",
  NDX:     "#06b6d4",
  DJI:     "#1e40af",
  EUSTX50: "#10b981",
  FTSEMIB: "#84cc16",
  SSE50:   "#f97316",
  HSI30:   "#ec4899",
};

function colorFor(code: string): string {
  return COLORS[code] ?? "#9ca3af";
}

export function RsiHistogramCard({ rsi, indices }: Props) {
  const [excluded, setExcluded] = useState<Set<string>>(new Set());

  const toggle = (code: string) => {
    setExcluded((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  };

  const data = useMemo(() => {
    return BIN_LABELS.map((label, i) => {
      const point: Record<string, string | number> = { bin: label };
      for (const idx of indices) {
        if (excluded.has(idx.code)) continue;
        point[idx.code] = rsi.by_index[idx.code]?.[i] ?? 0;
      }
      return point;
    });
  }, [indices, rsi, excluded]);

  const visibleIndices = indices.filter((i) => !excluded.has(i.code));

  return (
    <Card className="h-full">
      <CardContent className="p-4 flex flex-col h-full min-h-0">
        <div className="flex items-center justify-between mb-2 gap-2">
          <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            RSI distribution per indice
          </span>
          <span className="text-[10px] text-muted-foreground">click su legenda per nascondere/mostrare</span>
        </div>

        {/* Custom checkbox legend (above chart) */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mb-2">
          {indices.map((idx) => {
            const isOn = !excluded.has(idx.code);
            return (
              <button
                key={idx.code}
                type="button"
                onClick={() => toggle(idx.code)}
                className={cn(
                  "inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs transition-opacity",
                  !isOn && "opacity-40 hover:opacity-60",
                  isOn && "hover:bg-muted/40",
                )}
                title={isOn ? `Click per nascondere ${idx.code}` : `Click per mostrare ${idx.code}`}
              >
                <span
                  className="inline-block h-2.5 w-2.5 rounded-full shrink-0"
                  style={{ background: colorFor(idx.code) }}
                />
                <span className={cn("font-medium tabular-nums", !isOn && "line-through")}>
                  {idx.code}
                </span>
              </button>
            );
          })}
        </div>

        <div className="flex-1 min-h-0">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
              <XAxis dataKey="bin" fontSize={11} tickLine={false} axisLine={false} interval={1} />
              <YAxis fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} width={28} />
              <Tooltip
                contentStyle={{
                  fontSize: 12,
                  borderRadius: 6,
                  border: "1px solid var(--border, #e5e7eb)",
                  background: "var(--background, #fff)",
                }}
                labelFormatter={(label) => `RSI bin ${label}`}
              />
              {visibleIndices.map((idx) => (
                <Line
                  key={idx.code}
                  type="monotone"
                  dataKey={idx.code}
                  stroke={colorFor(idx.code)}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  activeDot={{ r: 5 }}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="text-[10px] text-muted-foreground mt-2 italic">
          Y = numero di stock per ciascun bin RSI(14). Bins 0-30 = oversold, 70-100 = overbought.
        </div>
      </CardContent>
    </Card>
  );
}
