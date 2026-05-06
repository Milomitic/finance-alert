import { Flame } from "lucide-react";
import { Link } from "react-router-dom";
import { useMemo, useState } from "react";

import type { Mover, MoversBlock } from "@/api/types";
import { StockIdentity } from "@/components/dashboard/StockIdentity";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
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
        className="flex items-center gap-2 px-3 py-1.5 hover:bg-accent/30 transition-colors min-w-0"
      >
        <StockIdentity ticker={m.ticker} name={m.name} />
        <span className={cn("text-sm font-semibold tabular-nums shrink-0", color)}>
          {v != null ? `${v >= 0 ? "+" : ""}${v.toFixed(2)}%` : "—"}
        </span>
      </Link>
    </li>
  );
}

/** One column header — small uppercase pill matching the rest of the
 *  dashboard's section dividers. Replaces the old Gainers/Losers tab
 *  toggle: now both lists are on screen at once. */
function ColumnHeader({ side }: { side: Side }) {
  return (
    <div
      className={cn(
        "shrink-0 px-3 py-1 text-[10.5px] uppercase tracking-[0.16em] font-bold border-b",
        side === "gainers"
          ? "bg-green-50/70 dark:bg-green-950/30 text-green-700 dark:text-green-300"
          : "bg-red-50/70 dark:bg-red-950/30 text-red-700 dark:text-red-300",
      )}
    >
      {side === "gainers" ? "Gainers" : "Losers"}
    </div>
  );
}

/**
 * Top-movers card. Was a single-list card with a Gainers/Losers tab;
 * the user wanted both visible at once, so we now render the two
 * lists side-by-side. The window picker (1G/1S/1M) stays in the
 * header — same data, different period.
 */
export function TopMoversCard({ movers }: Props) {
  const [window, setWindow] = useState<Window>("1d");
  const data = useMemo(() => getWindowed(movers, window), [movers, window]);
  const ROWS_PER_COL = 8;

  return (
    <Card className="h-full overflow-hidden">
      <CardContent className="p-0 flex flex-col h-full min-h-0">
        <div className="px-3 py-2 border-b bg-muted/30 shrink-0">
          <SectionTitle
            icon={Flame}
            label="Top movers"
            right={
              <Tabs value={window} onValueChange={(v) => setWindow(v as Window)}>
                <TabsList className="h-6 p-0.5">
                  <TabsTrigger value="1d" className="h-5 text-[10px] px-1.5" title="Variazione giornaliera">1G</TabsTrigger>
                  <TabsTrigger value="1w" className="h-5 text-[10px] px-1.5" title="Variazione settimanale (~5 giorni)">1S</TabsTrigger>
                  <TabsTrigger value="1m" className="h-5 text-[10px] px-1.5" title="Variazione mensile (~20 giorni)">1M</TabsTrigger>
                </TabsList>
              </Tabs>
            }
          />
        </div>

        {/* Two columns side-by-side. `divide-x` paints a 1px vertical
            border between them; each column flexes its rows
            independently. */}
        <div className="flex-1 min-h-0 grid grid-cols-2 divide-x divide-border/40">
          {(["gainers", "losers"] as const).map((side) => {
            const list = side === "gainers" ? data.gainers : data.losers;
            return (
              <div key={side} className="flex flex-col min-h-0 min-w-0">
                <ColumnHeader side={side} />
                {list.length === 0 ? (
                  <div className="flex-1 flex items-center justify-center p-4 text-xs text-muted-foreground">
                    Nessun dato
                  </div>
                ) : (
                  <ul className="flex-1 overflow-y-auto">
                    {list.slice(0, ROWS_PER_COL).map((m) => (
                      <MoverRow key={m.ticker} m={m} field={data.field} kind={side} />
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
