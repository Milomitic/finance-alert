import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ResponsiveContainer, Treemap } from "recharts";

import type { IndexBreadth, TreemapLeaf } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

interface Props {
  treemap: TreemapLeaf[];
  indices: IndexBreadth[];
}

function colorFor(change: number): string {
  if (change >= 2.0) return "#16a34a";
  if (change >= 1.0) return "#22c55e";
  if (change >= 0.0) return "#86efac";
  if (change >= -1.0) return "#fca5a5";
  if (change >= -2.0) return "#ef4444";
  return "#dc2626";
}

interface ContentProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  ticker?: string;
  change_pct?: number;
}

function CustomCell(props: ContentProps) {
  const { x = 0, y = 0, width = 0, height = 0, ticker = "", change_pct = 0 } = props;
  if (width < 2 || height < 2) return null;
  const showLabel = width > 40 && height > 22;
  const showChange = width > 60 && height > 36;
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={colorFor(change_pct)} stroke="#fff" strokeWidth={1} />
      {showLabel && (
        <text x={x + width / 2} y={y + height / 2} textAnchor="middle" fill="#fff" fontSize={12} fontWeight="bold">
          {ticker}
        </text>
      )}
      {showChange && (
        <text x={x + width / 2} y={y + height / 2 + 14} textAnchor="middle" fill="#fff" fontSize={11}>
          {change_pct >= 0 ? "+" : ""}{change_pct.toFixed(1)}%
        </text>
      )}
    </g>
  );
}

export function MarketTreemap({ treemap, indices }: Props) {
  const navigate = useNavigate();
  const [selected, setSelected] = useState<string>("all");
  const filtered = useMemo(() => {
    const src = selected === "all" ? treemap : treemap.filter((t) => t.index === selected);
    return src.map((t) => ({
      name: t.ticker,
      size: t.market_cap,
      ticker: t.ticker,
      change_pct: t.change_pct,
    }));
  }, [treemap, selected]);

  return (
    <Card>
      <CardContent className="p-4 h-full flex flex-col">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Treemap mkt-cap × performance</span>
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
        <div className="h-[260px] flex-1" title="Click su un tile per andare alla pagina dello stock">
          {filtered.length === 0 ? (
            <div className="h-full flex items-center justify-center text-sm text-muted-foreground">Nessun dato</div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <Treemap
                data={filtered}
                dataKey="size"
                content={<CustomCell />}
                onClick={(payload) => {
                  const ticker = (payload as { ticker?: string } | undefined)?.ticker;
                  if (ticker) navigate(`/stocks/${ticker}`);
                }}
              />
            </ResponsiveContainer>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
