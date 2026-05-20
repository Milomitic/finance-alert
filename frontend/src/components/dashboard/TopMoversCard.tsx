import { Flame } from "lucide-react";
import { Link } from "react-router-dom";
import { useMemo, useState } from "react";

import type { Mover, MoversBlock } from "@/api/types";
import {
  ScoreChip,
  fmtVolume,
} from "@/components/dashboard/LiveVolumeMoversCard";
import { StockIdentity } from "@/components/dashboard/StockIdentity";
import { Card, CardContent } from "@/components/ui/card";
import { FlashValue } from "@/components/ui/FlashValue";
import { SectionTitle } from "@/components/ui/section-title";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useLiveQuotes } from "@/hooks/useLiveQuote";
import { projectVolRatio } from "@/lib/intradayVolume";
import { cn } from "@/lib/utils";

interface Props {
  movers: MoversBlock;
  /** Market snapshot's `computed_at` — used as the time reference for
   *  projecting partial-day vol_ratio to end-of-day. Falls back to
   *  "now" inside the projector when null. */
  computedAt?: string | null;
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

function MoverRow({ m, field, live, computedAt, livePrice }: {
  m: Mover;
  field: WindowedMovers["field"];
  /** When true, colour by the value's own sign (a stock can flip
   *  gainer↔loser intraday so the column it lands in no longer
   *  dictates the colour). EOD windows keep the static sign. */
  live: boolean;
  /** Snapshot `computed_at` — threaded down so the row can project
   *  vol_ratio to end-of-day using the intraday curve. */
  computedAt?: string | null;
  /** Optional live price from the 15s batch poller, overlaid on top of
   *  the snapshot's `last_close`. Undefined → fall back to last_close. */
  livePrice?: number | null;
}) {
  const v = m[field] ?? null;
  const positive = v != null ? v >= 0 : true;
  const color = positive
    ? "text-green-600 dark:text-green-400"
    : "text-red-600 dark:text-red-400";
  const volToday = m.vol_today ?? null;
  const rawVolRatio = m.vol_ratio ?? null;
  // Project the snapshot's raw vol_ratio to end-of-day when we're
  // inside the US session. Outside session (or first ~30 min) the
  // helper returns `projected:false` and we just show the raw value.
  const projVol = projectVolRatio(rawVolRatio, computedAt);
  const displayVolRatio = projVol?.value ?? null;
  const isProjected = !!projVol?.projected;
  const composite = m.composite ?? null;
  const displayPrice = livePrice ?? m.last_close ?? null;
  return (
    <li className="border-b border-border/40 last:border-b-0">
      <Link
        to={`/stocks/${encodeURIComponent(m.ticker)}`}
        className="flex items-center gap-1.5 px-2 py-1.5 hover:bg-accent/30 transition-colors min-w-0"
      >
        {/* Identity — flexes; will truncate first when the row narrows. */}
        <StockIdentity ticker={m.ticker} name={m.name} />
        {/* Live/last price — between identity and % change so the eye
            reads "ticker → price → % move" left-to-right. When 1G is
            active and the polled overlay has a fresh price for this
            ticker we use that; otherwise we fall back to the snapshot's
            last_close. Wrapped in FlashValue → Wall-Street-tape flash
            (green uptick / rose downtick) on every polling refresh.
            `noTween` because list rows are many and simultaneous
            number-tweens would look noisy; flash alone is enough. */}
        <span
          className="shrink-0 text-[13px] font-semibold tabular-nums text-foreground/85 w-[58px] text-right"
          title={
            livePrice != null
              ? "Prezzo live (polling 15s)"
              : "Ultima chiusura disponibile"
          }
        >
          <FlashValue
            value={displayPrice}
            format={(p) => `$${p.toFixed(2)}`}
            noTween
          />
        </span>
        {/* % change — headline metric. Also flash-tinted on live
            updates: in 1G mode `change_pct` is overlaid from the
            polled quote, so the cell ticks each 15s like a real
            tape. The base sign-color (green/red) stays as the
            steady-state; the flash briefly overrides during the
            tween window per Wall-Street convention (a downtick on a
            positive % still shows rose for ~700ms then settles back
            to green). */}
        <span
          className={cn(
            "shrink-0 text-sm font-semibold tabular-nums w-[66px] text-right",
            color,
          )}
          title={
            live
              ? "Variazione % giornaliera (live)"
              : "Variazione % nella finestra selezionata"
          }
        >
          <FlashValue
            value={v}
            format={(p) => `${p >= 0 ? "+" : ""}${p.toFixed(2)}%`}
            noTween
          />
        </span>
        {/* Volume + multiplier — "12.4M (3.2×)". Font bumped 11→13px
            per user feedback: the figure was visually subordinate to
            % change but it carries comparable signal weight ("how
            unusual is today's activity"). The multiplier is
            INTRADAY-PROJECTED when the snapshot is partial-day — see
            `projectVolRatio` for the curve. We mark projected values
            with a "~" prefix so the user reads it as an estimate. */}
        <span
          className="shrink-0 text-[12.5px] tabular-nums text-muted-foreground/90 min-w-[92px] text-right"
          title={
            volToday != null
              ? `Volume oggi: ${volToday.toLocaleString("it-IT")} share${
                  displayVolRatio != null
                    ? ` · ${
                        isProjected
                          ? `proiezione fine giornata ~${displayVolRatio.toFixed(2)}× (scalato da ${projVol?.fraction ? Math.round(projVol.fraction * 100) : 0}% sessione)`
                          : `${displayVolRatio.toFixed(2)}× la media a 20 giorni`
                      }`
                    : ""
                }`
              : "Volume non disponibile"
          }
        >
          <span className="font-semibold text-foreground/80">
            {fmtVolume(volToday)}
          </span>
          {displayVolRatio != null && (
            <span
              className={cn(
                "ml-1",
                displayVolRatio >= 3
                  ? "text-orange-700 dark:text-orange-300 font-semibold"
                  : displayVolRatio >= 2
                  ? "text-foreground/70"
                  : "text-muted-foreground/70",
              )}
            >
              ({isProjected ? "~" : ""}
              {displayVolRatio.toFixed(1)}×)
            </span>
          )}
        </span>
        {/* Composite score chip — reuses the shared chip so the
            visual vocabulary matches LiveVolumeMoversCard exactly. */}
        <ScoreChip score={composite} />
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
export function TopMoversCard({ movers, computedAt }: Props) {
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

  // Live overlay carries both change_pct AND price now — price feeds
  // the new price column in the row layout. Previously the map stored
  // only change_pct (which dictated re-ranking) and the price column
  // didn't exist.
  const liveMap = useMemo(() => {
    const map = new Map<string, { change_pct: number; price: number | null }>();
    for (const q of liveQ.data?.quotes ?? []) {
      if (q.change_pct != null) {
        map.set(q.ticker, {
          change_pct: q.change_pct,
          price: q.price ?? null,
        });
      }
    }
    return map;
  }, [liveQ.data]);

  const data = useMemo<WindowedMovers>(() => {
    if (!isLive) return getWindowed(movers, window);
    // Combined pool, effective change = live ?? EOD fallback. (Price
    // overlay is applied in the row render, not the pool — sorting is
    // by change_pct only, so the pool only needs the live change_pct.)
    const seen = new Set<string>();
    const pool: Mover[] = [];
    for (const m of [...movers.gainers, ...movers.losers]) {
      if (seen.has(m.ticker)) continue;
      seen.add(m.ticker);
      const overlay = liveMap.get(m.ticker);
      pool.push(overlay != null ? { ...m, change_pct: overlay.change_pct } : m);
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
                        computedAt={computedAt}
                        livePrice={
                          liveActive ? liveMap.get(m.ticker)?.price ?? null : null
                        }
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
