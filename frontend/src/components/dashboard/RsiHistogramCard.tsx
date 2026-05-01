import { useState } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, XAxis, YAxis } from "recharts";

import type { IndexBreadth, RsiDistribution } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

interface Props {
  rsi: RsiDistribution;
  indices: IndexBreadth[];
}

const BIN_LABELS = ["0-10", "10-20", "20-30", "30-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"];

function colorFor(binIdx: number): string {
  if (binIdx < 3) return "#fb923c";
  if (binIdx >= 7) return "#dc2626";
  return "#9ca3af";
}

export function RsiHistogramCard({ rsi, indices }: Props) {
  const [selected, setSelected] = useState<string>("all");
  const bins = selected === "all" ? rsi.all : rsi.by_index[selected] ?? [];
  const data = bins.map((count, i) => ({ bin: BIN_LABELS[i], count, idx: i }));

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">RSI distribution</span>
          <Select value={selected} onValueChange={setSelected}>
            <SelectTrigger className="h-8 text-sm w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tutti</SelectItem>
              {indices.map((i) => (
                <SelectItem key={i.code} value={i.code}>{i.code}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="h-[160px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <XAxis dataKey="bin" fontSize={11} tickLine={false} axisLine={false} interval={1} />
              <YAxis fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} width={28} />
              <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                {data.map((d, i) => <Cell key={i} fill={colorFor(d.idx)} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
