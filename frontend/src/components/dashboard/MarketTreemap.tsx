import * as React from "react";
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

// Recharts 3.x passes a TreemapNode (with original data fields spread at root)
// to the content function. Use function form (not ReactNode) for reliability:
// the ReactNode form is brittle when libraries change cloneElement behavior.
interface CellNode {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  depth?: number;
  ticker?: string;
  change_pct?: number;
  name?: string;
  // Some Recharts versions nest the original row inside `payload`
  payload?: { ticker?: string; change_pct?: number };
}

function renderCell(node: CellNode): React.ReactElement {
  const x = node.x ?? 0;
  const y = node.y ?? 0;
  const width = node.width ?? 0;
  const height = node.height ?? 0;
  const ticker = node.ticker ?? node.payload?.ticker ?? node.name ?? "";
  const changePct = node.change_pct ?? node.payload?.change_pct ?? 0;
  if (width < 2 || height < 2) return <g />;
  const showLabel = width > 40 && height > 22;
  const showChange = width > 60 && height > 36;
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={colorFor(changePct)} stroke="#fff" strokeWidth={1} />
      {showLabel && (
        <text x={x + width / 2} y={y + height / 2} textAnchor="middle" fill="#fff" fontSize={12} fontWeight="bold">
          {ticker}
        </text>
      )}
      {showChange && (
        <text x={x + width / 2} y={y + height / 2 + 14} textAnchor="middle" fill="#fff" fontSize={11}>
          {changePct >= 0 ? "+" : ""}{changePct.toFixed(1)}%
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
        <div className="flex-1 min-h-[220px]" title="Click su un tile per andare alla pagina dello stock">
          {filtered.length === 0 ? (
            <div className="h-full flex items-center justify-center text-sm text-muted-foreground">Nessun dato</div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <Treemap
                data={filtered}
                dataKey="size"
                nameKey="ticker"
                content={renderCell as never}
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
