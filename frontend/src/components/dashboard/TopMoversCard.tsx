import { TrendingDown, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";
import { useMemo, useState } from "react";

import type { Mover, MoversBlock } from "@/api/types";
import { IndexBadge } from "@/components/dashboard/IndexBadge";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

interface Props {
  movers: MoversBlock;
}

type Window = "1d" | "1w" | "1m";

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
  kind: "gainer" | "loser";
}) {
  const v = m[field] ?? null;
  const color =
    kind === "gainer"
      ? "text-green-600 dark:text-green-400"
      : "text-red-600 dark:text-red-400";
  return (
    <li className="border-b border-border/40 last:border-b-0">
      <Link
        to={`/stocks/${encodeURIComponent(m.ticker)}`}
        className="flex items-center gap-2 px-3 py-2 hover:bg-accent/30 transition-colors"
      >
        <StockLogo ticker={m.ticker} size="xs" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-bold tabular-nums">{m.ticker}</span>
            <IndexBadge code={m.index} size="xs" showCode={false} />
          </div>
          {m.name && (
            <div className="text-[10px] text-muted-foreground truncate" title={m.name}>{m.name}</div>
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
 * Top movers card with a Daily/Weekly/Monthly window picker.
 * For each window, splits into Gainers (left col) + Losers (right col) — top 5 each.
 */
export function TopMoversCard({ movers }: Props) {
  const [window, setWindow] = useState<Window>("1d");
  const data = useMemo(() => getWindowed(movers, window), [movers, window]);

  return (
    <Card>
      <CardContent className="p-0">
        <Tabs value={window} onValueChange={(v) => setWindow(v as Window)}>
          <div className="flex items-center gap-3 px-4 py-2.5 border-b bg-muted/40">
            <span className="text-sm font-semibold uppercase tracking-wide">Top movers</span>
            <TabsList className="h-8 ml-auto">
              <TabsTrigger value="1d" className="h-7 text-xs px-3">Giornaliera</TabsTrigger>
              <TabsTrigger value="1w" className="h-7 text-xs px-3">Settimanale</TabsTrigger>
              <TabsTrigger value="1m" className="h-7 text-xs px-3">Mensile</TabsTrigger>
            </TabsList>
          </div>
          <TabsContent value={window} className="m-0">
            <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-border/50">
              <div>
                <div className="flex items-center gap-1.5 px-3 py-1.5 bg-green-50/50 dark:bg-green-950/20 border-b border-border/50">
                  <TrendingUp className="h-3.5 w-3.5 text-green-600 dark:text-green-400" />
                  <span className="text-[11px] uppercase tracking-wider font-bold text-green-700 dark:text-green-300">
                    Gainers
                  </span>
                </div>
                {data.gainers.length === 0 ? (
                  <div className="text-xs text-muted-foreground p-4 text-center">Nessun dato</div>
                ) : (
                  <ul>
                    {data.gainers.slice(0, 5).map((m) => (
                      <MoverRow key={`g-${m.ticker}`} m={m} field={data.field} kind="gainer" />
                    ))}
                  </ul>
                )}
              </div>
              <div>
                <div className="flex items-center gap-1.5 px-3 py-1.5 bg-red-50/50 dark:bg-red-950/20 border-b border-border/50">
                  <TrendingDown className="h-3.5 w-3.5 text-red-600 dark:text-red-400" />
                  <span className="text-[11px] uppercase tracking-wider font-bold text-red-700 dark:text-red-300">
                    Losers
                  </span>
                </div>
                {data.losers.length === 0 ? (
                  <div className="text-xs text-muted-foreground p-4 text-center">Nessun dato</div>
                ) : (
                  <ul>
                    {data.losers.slice(0, 5).map((m) => (
                      <MoverRow key={`l-${m.ticker}`} m={m} field={data.field} kind="loser" />
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
