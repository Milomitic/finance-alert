import { Flame } from "lucide-react";
import { Link } from "react-router-dom";
import { useMemo, useState } from "react";

import type { Mover, MoversBlock } from "@/api/types";
import { StockIdentity } from "@/components/dashboard/StockIdentity";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useLiveQuotes } from "@/hooks/useLiveQuote";
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

// Batch live-quote endpoint caps at 50 tickers/request — keep the live
// candidate pool under that.
const MAX_LIVE_TICKERS = 50;
const ROWS_PER_COL = 8;

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

function MoverRow({ m, field, live }: {
  m: Mover;
  field: WindowedMovers["field"];
  /** When true, colour by the value's own sign (a stock can flip
   *  gainer↔loser intraday so the column it lands in no longer
   *  dictates the colour). EOD windows keep the static sign. */
  live: boolean;
}) {
  const v = m[field] ?? null;
  const positive = v != null ? v >= 0 : true;
  const color = positive
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
          {live ? <span className="ml-0.5 align-top text-[8px] text-muted-foreground">●</span> : null}
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
 *
 * Near-real-time 1G ranking
 * ─────────────────────────
 * The server-side movers block is EOD-derived (`change_pct =
 * (last_close − prev_close)/prev_close` off daily bars) and only moves
 * when a scan re-ingests OHLCV. For the **1G** window we re-rank it
 * intraday: every 15s we batch-poll live quotes for the EOD top
 * gainers∪losers (the candidate pool), substitute each row's
 * `change_pct` with the live value (same %-points scale,
 * `change_abs/prev_close*100`), then re-sort both columns from the
 * combined pool — so a stock can flip gainer↔loser as prices move.
 *
 * Deliberate scope limit: the *candidate pool* stays EOD-bounded. A
 * stock that explodes intraday but wasn't an EOD top mover won't
 * surface — true whole-universe intraday ranking would mean live-
 * quoting ~1100 tickers every 15s (infeasible vs yfinance limits).
 * 1S/1M stay pure EOD (live quotes only carry today's move).
 */
export function TopMoversCard({ movers }: Props) {
  const [window, setWindow] = useState<Window>("1d");
  const isLive = window === "1d";

  // Live candidate pool: the union of the EOD 1G gainers+losers. These
  // are the only tickers whose intraday rank we can refresh without
  // live-quoting the whole catalog.
  const candidateTickers = useMemo(() => {
    if (!isLive) return [];
    const seen = new Set<string>();
    const out: string[] = [];
    for (const m of [...movers.gainers, ...movers.losers]) {
      if (!seen.has(m.ticker)) {
        seen.add(m.ticker);
        out.push(m.ticker);
      }
    }
    return out.slice(0, MAX_LIVE_TICKERS);
  }, [isLive, movers.gainers, movers.losers]);

  // 15s batch poll (server-cached 10s). Disabled on 1S/1M so we don't
  // burn quota for windows that can't use live prices anyway.
  const liveQ = useLiveQuotes(candidateTickers, isLive);

  const liveMap = useMemo(() => {
    const map = new Map<string, number>();
    for (const q of liveQ.data?.quotes ?? []) {
      if (q.change_pct != null) map.set(q.ticker, q.change_pct);
    }
    return map;
  }, [liveQ.data]);

  const data = useMemo<WindowedMovers>(() => {
    if (!isLive) return getWindowed(movers, window);
    // Combined pool, effective change = live ?? EOD fallback.
    const seen = new Set<string>();
    const pool: Mover[] = [];
    for (const m of [...movers.gainers, ...movers.losers]) {
      if (seen.has(m.ticker)) continue;
      seen.add(m.ticker);
      const liveVal = liveMap.get(m.ticker);
      pool.push(liveVal != null ? { ...m, change_pct: liveVal } : m);
    }
    const withChange = pool.filter((m) => m.change_pct != null);
    const gainers = [...withChange].sort(
      (a, b) => (b.change_pct as number) - (a.change_pct as number),
    );
    // Losers from the same pool, opposite end — exclude tickers already
    // shown as gainers so a small pool can't double-list the same row.
    const topGainers = new Set(
      gainers.slice(0, ROWS_PER_COL).map((m) => m.ticker),
    );
    const losers = [...withChange]
      .filter((m) => !topGainers.has(m.ticker))
      .sort((a, b) => (a.change_pct as number) - (b.change_pct as number));
    return { gainers, losers, field: "change_pct" };
  }, [isLive, movers, window, liveMap]);

  const liveActive = isLive && liveMap.size > 0;

  return (
    <Card className="h-full overflow-hidden">
      <CardContent className="p-0 flex flex-col h-full min-h-0">
        <div className="px-3 py-2 border-b bg-muted/30 shrink-0">
          <SectionTitle
            icon={Flame}
            label="Top movers"
            right={
              <div className="flex items-center gap-2">
                {liveActive ? (
                  <span
                    className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-green-600 dark:text-green-400"
                    title="Ranking 1G aggiornato dai prezzi live ogni 15s"
                  >
                    <span className="relative flex h-1.5 w-1.5">
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-500 opacity-75" />
                      <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-green-500" />
                    </span>
                    Live
                  </span>
                ) : null}
                <Tabs value={window} onValueChange={(v) => setWindow(v as Window)}>
                  <TabsList className="h-6 p-0.5">
                    <TabsTrigger value="1d" className="h-5 text-[10px] px-1.5" title="Variazione giornaliera — ranking live ogni 15s">1G</TabsTrigger>
                    <TabsTrigger value="1w" className="h-5 text-[10px] px-1.5" title="Variazione settimanale (~5 giorni)">1S</TabsTrigger>
                    <TabsTrigger value="1m" className="h-5 text-[10px] px-1.5" title="Variazione mensile (~20 giorni)">1M</TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>
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
                      <MoverRow
                        key={m.ticker}
                        m={m}
                        field={data.field}
                        live={liveActive && liveMap.has(m.ticker)}
                      />
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
