import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { AlertsByDayPoint } from "@/api/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Props {
  data: AlertsByDayPoint[];
  compact?: boolean;
}

const KIND_LABEL: Record<string, string> = {
  rsi_oversold: "RSI Oversold",
  rsi_overbought: "RSI Overbought",
  golden_cross: "Golden Cross",
  death_cross: "Death Cross",
};

interface TooltipPayloadEntry {
  payload: AlertsByDayPoint;
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayloadEntry[] }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="rounded border bg-popover p-2 text-xs shadow">
      <div className="font-medium mb-1">
        {new Date(point.date).toLocaleDateString("it-IT")}
      </div>
      <div className="tabular-nums mb-1">
        Totale: <strong>{point.count}</strong>
      </div>
      {Object.entries(point.by_kind).map(([kind, count]) => (
        <div key={kind} className="text-muted-foreground">
          {KIND_LABEL[kind] ?? kind}: {count}
        </div>
      ))}
    </div>
  );
}

export function AlertsByDayChart({ data, compact = false }: Props) {
  return (
    <Card>
      {!compact && (
        <CardHeader>
          <CardTitle className="text-base">Alert per giorno (ultimi 30gg)</CardTitle>
        </CardHeader>
      )}
      <CardContent>
        <div className={compact ? "h-[80px]" : "h-[260px]"}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 5, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
              <XAxis
                dataKey="date"
                tickFormatter={(iso) =>
                  new Date(iso).toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit" })
                }
                fontSize={11}
              />
              <YAxis allowDecimals={false} fontSize={11} />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="count"
                stroke="var(--primary, #3b82f6)"
                fill="var(--primary, #3b82f6)"
                fillOpacity={0.2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
