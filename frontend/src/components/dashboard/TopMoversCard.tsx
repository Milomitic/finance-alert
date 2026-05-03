import { TrendingDown, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";
import { useMemo, useState } from "react";

import type { Mover, MoversBlock } from "@/api/types";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

interface Props {
  movers: MoversBlock;
}

type Window = "1d" | "1w" | "1m";
type Side = "gainers" | "losers";

interface WindowedMovers {
  gainers: Mover[];
  losers: Mover[];
  field: keyof Pick<Mover, "change_pct" | "change_pct_5d" | "change_pct_20d">;
}

function getWindowed(movers: MoversBlock, w: Window): WindowedMovers {
  if (w === "1w") {
    return {
      gainers: movers.gainers_5d ?? [],
      losers: movers.losers_5d ?? [],
      field: "change_pct_5d",
    };
  }
  if (w === "1m") {
    return {
      gainers: movers.gainers_20d ?? [],
      losers: movers.losers_20d ?? [],
      field: "change_pct_20d",
    };
  }
  return { gainers: movers.gainers, losers: movers.losers, field: "change_pct" };
}

function MoverRow({ m, field, kind }: {
  m: Mover;
  field: WindowedMovers["field"];
  kind: Side;
}) {
  const v = m[field] ?? null;
  const color =
    kind === "gainers"
      ? "text-green-600 dark:text-green-400"
      : "text-red-600 dark:text-red-400";
  return (
    <li className="border-b border-border/40 last:border-b-0">
      <Link
        to={`/stocks/${encodeURIComponent(m.ticker)}`}
        className="flex items-center gap-2 px-3 py-1.5 hover:bg-accent/30 transition-colors"
      >
        <StockLogo ticker={m.ticker} size="xs" />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-bold tabular-nums leading-tight">{m.ticker}</div>
          {m.name && (
            <div className="text-[10px] text-muted-foreground truncate leading-tight" title={m.name}>{m.name}</div>
          )}
        </div>
        <span className={cn("text-sm font-semibold tabular-nums shrink-0", color)}>
          {v != null ? `${v >= 0 ? "+" : ""}${v.toFixed(2)}%` : "—"}
        </span>
      </Link>
    </li>
  );
}

/**
 * Compact top-movers card sized for a 4-column dashboard row.
 *
 * Has two pickers: time window (1d/1w/1m) and side (gainers/losers). Showing
 * both lists side-by-side would be too cramped at this width, so the user
 * toggles between them with a small Top Gainers / Top Losers tab.
 */
export function TopMoversCard({ movers }: Props) {
  const [window, setWindow] = useState<Window>("1d");
  const [side, setSide] = useState<Side>("gainers");
  const data = useMemo(() => getWindowed(movers, window), [movers, window]);
  const list = side === "gainers" ? data.gainers : data.losers;

  return (
    <Card className="h-full overflow-hidden">
      <CardContent className="p-0 flex flex-col h-full min-h-0">
        <div className="flex items-center gap-1.5 px-3 py-2 border-b bg-muted/30 shrink-0">
          {side === "gainers" ? (
            <TrendingUp className="h-3.5 w-3.5 text-green-600 dark:text-green-400" />
          ) : (
            <TrendingDown className="h-3.5 w-3.5 text-red-600 dark:text-red-400" />
          )}
          <span className="text-[10px] uppercase tracking-wider font-bold">Top movers</span>
          <Tabs value={window} onValueChange={(v) => setWindow(v as Window)} className="ml-auto">
            <TabsList className="h-6 p-0.5">
              <TabsTrigger value="1d" className="h-5 text-[10px] px-1.5" title="Variazione giornaliera">1G</TabsTrigger>
              <TabsTrigger value="1w" className="h-5 text-[10px] px-1.5" title="Variazione settimanale (~5 giorni)">1S</TabsTrigger>
              <TabsTrigger value="1m" className="h-5 text-[10px] px-1.5" title="Variazione mensile (~20 giorni)">1M</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>

        {/* Gainers/Losers side toggle */}
        <div className="flex shrink-0 border-b">
          <button
            type="button"
            onClick={() => setSide("gainers")}
            className={cn(
              "flex-1 text-[11px] font-bold uppercase tracking-wider py-1.5 transition-colors",
              side === "gainers"
                ? "bg-green-50/70 dark:bg-green-950/30 text-green-700 dark:text-green-300"
                : "text-muted-foreground hover:bg-muted/30",
            )}
          >
            Gainers
          </button>
          <button
            type="button"
            onClick={() => setSide("losers")}
            className={cn(
              "flex-1 text-[11px] font-bold uppercase tracking-wider py-1.5 border-l transition-colors",
              side === "losers"
                ? "bg-red-50/70 dark:bg-red-950/30 text-red-700 dark:text-red-300"
                : "text-muted-foreground hover:bg-muted/30",
            )}
          >
            Losers
          </button>
        </div>

        <TabsContentArea>
          {list.length === 0 ? (
            <div className="flex-1 flex items-center justify-center p-4 text-xs text-muted-foreground">
              Nessun dato
            </div>
          ) : (
            <ul className="flex-1 overflow-y-auto">
              {list.slice(0, 8).map((m) => (
                <MoverRow key={m.ticker} m={m} field={data.field} kind={side} />
              ))}
            </ul>
          )}
        </TabsContentArea>
      </CardContent>
    </Card>
  );
}

function TabsContentArea({ children }: { children: React.ReactNode }) {
  return <div className="flex-1 min-h-0 flex flex-col">{children}</div>;
}
