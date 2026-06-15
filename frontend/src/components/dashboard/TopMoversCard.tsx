import { Flame } from "lucide-react";
import { Link } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";

import type { Mover, MoversBlock } from "@/api/types";
import {
  ScoreChip,
  fmtVolume,
} from "@/components/dashboard/LiveVolumeMoversCard";
import {
  MarketStateBadge,
  deriveMarketPhase,
} from "@/components/dashboard/MarketStateBadge";
import { StockIdentity } from "@/components/dashboard/StockIdentity";
import { Card, CardContent } from "@/components/ui/card";
import { FlashValue } from "@/components/ui/FlashValue";
import { SectionTitle } from "@/components/ui/section-title";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useLiveQuotes } from "@/hooks/useLiveQuote";
import { useFlipList } from "@/hooks/useFlipList";
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

// Live candidate pool size. The backend caps each HTTP request at 50
// tickers, but `useLiveQuotes` now chunks + parallelises, so the pool
// can be wider. 120 covers the union of every EOD mover list (gainers/
// losers across 1d/1w/1m windows + top-volume + volume-spikes + 52w
// extremes) — the set of names that have DEMONSTRATED they can move,
// which is where intraday movers realistically come from. A flat-for-
// months name suddenly topping the board is vanishingly rare, so this
// bounded superset captures ~all realistic intraday movers without
// live-quoting the whole ~1100-name catalog.
const MAX_LIVE_TICKERS = 120;
const ROWS_PER_COL = 9;

// Exchanges that follow the US intraday-volume curve used by `projectVolRatio`.
// Only these get the partial-day → end-of-day volume PROJECTION. A Hong Kong
// (or European) listing is already a complete trading day by the time the
// US-session snapshot runs, so projecting it would inflate the figure — those
// rows show their definitive volume instead.
const US_SESSION_EXCHANGES = new Set(["NASDAQ", "NYSE", "NYSE Arca"]);

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

function MoverRow({ m, field, window, live, computedAt, livePrice, livePulse, flipRef }: {
  m: Mover;
  field: WindowedMovers["field"];
  /** Active window — drives WHICH volume to show: today's (1d, projected
   *  to EOD for US names) vs the period total (1w → vol_5d, 1m → vol_20d). */
  window: Window;
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
  /** True when this row is being polled live AND its market is open/pre —
   *  drives the pulsing green dot next to the ticker (same as the Volumi
   *  maggiori card). */
  livePulse?: boolean;
  /** FLIP register-ref from useFlipList — animates rank changes. */
  flipRef?: (el: HTMLElement | null) => void;
}) {
  const v = m[field] ?? null;
  const positive = v != null ? v >= 0 : true;
  const color = positive
    ? "text-green-600 dark:text-green-400"
    : "text-red-600 dark:text-red-400";
  const composite = m.composite ?? null;
  const displayPrice = livePrice ?? m.last_close ?? null;

  // ── Window-aware volume ────────────────────────────────────────────────
  // 1d  → today's share volume; PROJECTED to end-of-day (with "~") for
  //       US-session names that are still mid-session, definitive otherwise.
  // 1w  → vol_5d  (sum of the last 5 daily volumes) — a period total, final.
  // 1m  → vol_20d (sum of the last 20 daily volumes) — a period total, final.
  // The "× vs 20d avg" multiplier only makes sense for the single-day view,
  // so it's shown for 1d only.
  const isUS = m.exchange != null && US_SESSION_EXCHANGES.has(m.exchange);
  let volValue: number | null;
  let volEstimated = false;            // → render a "~" prefix on the volume
  let multiplier: number | null = null; // the "× vs media" badge (1d only)
  let multiplierEstimated = false;
  if (window === "1d") {
    const rawVol = m.vol_today ?? null;
    // Only US-session names follow the projection curve; HK/EU bars are
    // already a full day at snapshot time → show them as-is.
    const proj = isUS ? projectVolRatio(m.vol_ratio ?? null, computedAt) : null;
    if (proj?.projected && proj.fraction > 0) {
      volValue = rawVol != null ? Math.round(rawVol / proj.fraction) : null;
      volEstimated = true;
      multiplier = proj.value;
      multiplierEstimated = true;
    } else {
      volValue = rawVol;
      multiplier = m.vol_ratio ?? null; // definitive (closed market / non-US)
    }
  } else if (window === "1w") {
    volValue = m.vol_5d ?? null;
  } else {
    volValue = m.vol_20d ?? null;
  }
  const volWindowLabel = window === "1d" ? "oggi" : window === "1w" ? "5 giorni" : "20 giorni";
  const volTitle =
    volValue != null
      ? `Volume ${volWindowLabel}: ${volValue.toLocaleString("it-IT")} share${
          volEstimated ? " (stima fine giornata, definitiva a chiusura)" : ""
        }${
          multiplier != null
            ? ` · ${multiplierEstimated ? "~" : ""}${multiplier.toFixed(2)}× la media a 20 giorni`
            : ""
        }`
      : "Volume non disponibile";
  return (
    <li ref={flipRef} className="border-b border-border/40 last:border-b-0">
      {/* One fixed-column grid per row — same column-per-info-type layout as
          the Volumi maggiori card, so price / %change / volume / multiplier /
          score line up vertically across every row. The identity cell flexes
          (minmax(0,1fr)) and truncates first when the column narrows. */}
      <Link
        to={`/stocks/${encodeURIComponent(m.ticker)}`}
        className="grid grid-cols-[minmax(0,1fr)_46px_52px_48px_30px_auto] items-center gap-1 px-1.5 py-1.5 hover:bg-accent/30 transition-colors"
      >
        {/* Col 1: identity + per-row live-poll dot. A classic pulsing green
            dot sits right of the ticker for every row whose 15s polling is
            active AND whose market is open/pre — surfaces "this price is
            live" at a glance (same treatment as the Volumi maggiori card). */}
        <div className="flex items-center gap-1.5 min-w-0">
          <StockIdentity ticker={m.ticker} name={m.name} />
          {livePulse && (
            <span
              className="relative inline-flex h-2 w-2 shrink-0"
              title="Pollato live (refresh ogni 15s)"
              aria-label="live"
            >
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-500 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </span>
          )}
        </div>
        {/* Col 2: live/last price. FlashValue → Wall-Street-tape tint on each
            15s refresh; `noTween` keeps a long list calm. */}
        <span
          className="text-[13px] font-semibold tabular-nums text-foreground/85 text-right"
          title={livePrice != null ? "Prezzo live (polling 15s)" : "Ultima chiusura disponibile"}
        >
          <FlashValue value={displayPrice} format={(p) => `$${p.toFixed(2)}`} noTween />
        </span>
        {/* Col 3: % change — headline metric, sign-coloured. */}
        <span
          className={cn("text-sm font-semibold tabular-nums text-right", color)}
          title={live ? "Variazione % giornaliera (live)" : "Variazione % nella finestra selezionata"}
        >
          <FlashValue value={v} format={(p) => `${p >= 0 ? "+" : ""}${p.toFixed(2)}%`} noTween />
        </span>
        {/* Col 4: volume (number only — multiplier moved to its own column so
            the columns stay aligned). Window-aware per volValue above. */}
        <span
          className="text-[12.5px] tabular-nums text-right font-semibold text-foreground/80"
          title={volTitle}
        >
          {volEstimated ? "~" : ""}
          {fmtVolume(volValue)}
        </span>
        {/* Col 5: × vs 20d-avg multiplier (1d only; empty cell otherwise so
            the score column never shifts between windows). */}
        <span className="text-[11px] font-mono tabular-nums text-center" title={volTitle}>
          {window === "1d" && multiplier != null ? (
            <span
              className={cn(
                multiplier >= 3
                  ? "text-orange-700 dark:text-orange-300 font-semibold"
                  : multiplier >= 2
                    ? "text-foreground/70"
                    : "text-muted-foreground/60",
              )}
            >
              {multiplierEstimated ? "~" : ""}
              {multiplier.toFixed(1)}×
            </span>
          ) : null}
        </span>
        {/* Col 6: composite score chip — shared component, same as Volumi. */}
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
 * intraday: every 15s we batch-poll live quotes for a WIDE candidate
 * pool (the union of every EOD mover list — see candidateTickers),
 * substitute each row's `change_pct` with the live value, then re-sort
 * both columns from that pool — so a stock can flip gainer↔loser AND a
 * name that wasn't a top EOD mover can climb in as it moves intraday.
 *
 * Scope: the candidate pool is the union of all mover lists (1d/1w/1m
 * gainers+losers, top-volume, volume-spikes, 52w high/low), bounded at
 * MAX_LIVE_TICKERS=120 and polled via chunked parallel requests. This
 * covers the names that have demonstrated they can move — true whole-
 * universe intraday ranking (~1100 tickers every 15s) stays infeasible
 * vs yfinance limits, but a flat-for-months name suddenly topping the
 * board is vanishingly rare, so the bounded superset captures ~all
 * realistic intraday movers. 1S/1M stay pure EOD.
 */
/* Last LIVE-ranked board, persisted per browser session. On a hard reload
 * the movers payload renders instantly with the EOD/stale ranking while the
 * first 15s live batch is still in flight (~2s) — the user saw "yesterday's
 * board" flash before the live re-rank snapped in. Seeding the initial
 * render from this snapshot (max 10 min old) makes reloads visually
 * continuous; the first live batch then takes over with a FLIP slide. */
const SNAP_KEY = "topmovers-live-board-v1";

function readBoardSnapshot(): WindowedMovers | null {
  try {
    const raw = sessionStorage.getItem(SNAP_KEY);
    if (!raw) return null;
    const s = JSON.parse(raw) as { ts: number; data: WindowedMovers };
    if (!s?.data?.gainers || Date.now() - s.ts > 10 * 60_000) return null;
    return s.data;
  } catch {
    return null;
  }
}

export function TopMoversCard({ movers, computedAt }: Props) {
  const [window, setWindow] = useState<Window>("1d");
  const [boardSeed] = useState(readBoardSnapshot);
  const registerFlip = useFlipList();
  const isLive = window === "1d";

  // Live candidate pool: the union of EVERY EOD mover list — not just
  // the displayed 1G gainers/losers. Polling only the already-shown
  // names froze the live ranking (a stock outside the top-8 could
  // never rise into it because we never polled it). Widening to all
  // mover lists (1d/1w/1m gainers+losers, top-volume, volume-spikes,
  // 52w high/low, PLUS the high-beta/leveraged-bull pool) means a name
  // ranked #40 by EOD — or a leveraged ETF like SOXL/TNA that was flat
  // yesterday — can climb to #1 on live prices and surface. Bounded at
  // MAX_LIVE_TICKERS; useLiveQuotes chunks the pool into parallel
  // <=50 requests.
  const candidateTickers = useMemo(() => {
    if (!isLive) return [];
    const seen = new Set<string>();
    const out: string[] = [];
    const lists: (Mover[] | undefined)[] = [
      movers.gainers, movers.losers,
      movers.gainers_5d, movers.losers_5d,
      movers.gainers_20d, movers.losers_20d,
      movers.top_volume, movers.volume_spikes,
      movers.new_52w_high, movers.new_52w_low,
      // Leveraged-bull ETFs (SOXL/TNA…) + highest-volatility names —
      // always polled so they can climb into the live ranking even on a
      // day they didn't make the EOD top-N.
      movers.high_beta,
    ];
    for (const list of lists) {
      for (const m of list ?? []) {
        if (m && m.ticker && !seen.has(m.ticker)) {
          seen.add(m.ticker);
          out.push(m.ticker);
        }
      }
    }
    return out.slice(0, MAX_LIVE_TICKERS);
  }, [isLive, movers]);

  // 15s batch poll (server-cached 10s). Disabled on 1S/1M so we don't
  // burn quota for windows that can't use live prices anyway.
  const liveQ = useLiveQuotes(candidateTickers, isLive);

  // Live overlay carries both change_pct AND price now — price feeds
  // the new price column in the row layout. Previously the map stored
  // only change_pct (which dictated re-ranking) and the price column
  // didn't exist.
  const liveMap = useMemo(() => {
    const map = new Map<
      string,
      { change_pct: number; price: number | null; is_open: boolean; fresh: boolean }
    >();
    const todayISO = new Date().toISOString().slice(0, 10);
    for (const q of liveQ.data?.quotes ?? []) {
      if (q.change_pct != null) {
        const isOpen = q.market_state === "OPEN" || q.market_state === "PRE";
        map.set(q.ticker, {
          change_pct: q.change_pct,
          price: q.price ?? null,
          // OPEN and PRE both carry a fresh live/pre-market price → pulse dot.
          is_open: isOpen,
          // TODAY's data (live session or post-close provisional). A failed
          // fetch degrades to the EOD fallback carrying YESTERDAY's change
          // (as_of < today, state CLOSED) — that must never be ranked as if
          // it were a live move (the frozen-at-the-open report, 2026-06-11).
          fresh: isOpen || q.as_of_date === todayISO,
        });
      }
    }
    return map;
  }, [liveQ.data]);

  const data = useMemo<WindowedMovers>(() => {
    if (!isLive) return getWindowed(movers, window);
    // Reload continuity: until the first live batch resolves, show the last
    // live board from this session instead of the stale EOD ranking.
    if (liveMap.size === 0 && boardSeed) return boardSeed;
    // Combined pool from EVERY mover list (same union as the live
    // candidate pool) so a name that wasn't an EOD top-gainer but
    // moves intraday can climb into the displayed list. Effective
    // change = live ?? EOD fallback. (Price overlay is applied in the
    // row render; sorting is by change_pct only.)
    const seen = new Set<string>();
    const pool: Mover[] = [];
    const freshPool: Mover[] = [];
    const lists: (Mover[] | undefined)[] = [
      movers.gainers, movers.losers,
      movers.gainers_5d, movers.losers_5d,
      movers.gainers_20d, movers.losers_20d,
      movers.top_volume, movers.volume_spikes,
      movers.new_52w_high, movers.new_52w_low,
      // Leveraged-bull ETFs (SOXL/TNA…) + highest-volatility names —
      // always polled so they can climb into the live ranking even on a
      // day they didn't make the EOD top-N.
      movers.high_beta,
    ];
    for (const list of lists) {
      for (const m of list ?? []) {
        if (!m || !m.ticker || seen.has(m.ticker)) continue;
        seen.add(m.ticker);
        const overlay = liveMap.get(m.ticker);
        pool.push(overlay != null ? { ...m, change_pct: overlay.change_pct } : m);
        if (overlay?.fresh) {
          freshPool.push({ ...m, change_pct: overlay.change_pct });
        }
      }
    }
    // While the session is OPEN, rank ONLY rows with TODAY's data: at the
    // bell most fetches are still EOD fallbacks carrying yesterday's ±6%
    // d/d change, which would dominate today's real ±1% early moves and
    // freeze the board on yesterday's set. The fresh subset grows poll by
    // poll (15s); until the FIRST fresh quote arrives we keep the full EOD
    // pool so the card never flashes empty.
    const anyOpen = (liveQ.data?.quotes ?? []).some((q) => q.market_state === "OPEN");
    const ranked = anyOpen && freshPool.length > 0 ? freshPool : pool;
    const withChange = ranked.filter((m) => m.change_pct != null);
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
  }, [isLive, movers, window, liveMap, liveQ.data, boardSeed]);

  // Persist the live-ranked board for reload continuity (trimmed to the
  // visible rows; sessionStorage = per-tab, dies with the browser session).
  useEffect(() => {
    if (!isLive || liveMap.size === 0) return;
    try {
      sessionStorage.setItem(SNAP_KEY, JSON.stringify({
        ts: Date.now(),
        data: {
          gainers: data.gainers.slice(0, ROWS_PER_COL),
          losers: data.losers.slice(0, ROWS_PER_COL),
          field: data.field,
        },
      }));
    } catch { /* storage full/blocked — cosmetic feature, ignore */ }
  }, [data, isLive, liveMap.size]);

  const liveActive = isLive && liveMap.size > 0;
  // Aggregate market phase across the polled quotes → LIVE / PRE / Closed
  // badge. During pre-market the quotes carry market_state="PRE", so the
  // badge reads PRE and the user knows the % is the pre-open move.
  const phase = useMemo(
    () => deriveMarketPhase((liveQ.data?.quotes ?? []).map((q) => q.market_state)),
    [liveQ.data],
  );

  return (
    <Card className="h-full overflow-hidden">
      <CardContent className="p-0 flex flex-col h-full min-h-0">
        <div className="px-3 py-2 border-b bg-muted/30 shrink-0">
          <SectionTitle
            icon={Flame}
            label="Top movers"
            right={
              <div className="flex items-center gap-2">
                {liveActive ? <MarketStateBadge phase={phase} /> : null}
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
            border between them. Natural height (no flex-1/overflow): the
            lists are capped at ROWS_PER_COL so they flow to content and the
            card grows to fit — the dashboard grid then equalizes all three
            spotlight cards to the tallest, with no internal scroll. */}
        <div className="grid grid-cols-2 divide-x divide-border/40">
          {(["gainers", "losers"] as const).map((side) => {
            const list = side === "gainers" ? data.gainers : data.losers;
            return (
              <div key={side} className="flex flex-col min-w-0 overflow-x-hidden">
                <ColumnHeader side={side} />
                {list.length === 0 ? (
                  <div className="flex-1 flex items-center justify-center p-4 text-xs text-muted-foreground">
                    Nessun dato
                  </div>
                ) : (
                  <ul>
                    {list.slice(0, ROWS_PER_COL).map((m) => {
                      const lq = liveActive ? liveMap.get(m.ticker) : undefined;
                      return (
                        <MoverRow
                          key={m.ticker}
                          flipRef={registerFlip(side + ':' + m.ticker)}
                          m={m}
                          field={data.field}
                          window={window}
                          live={liveActive && liveMap.has(m.ticker)}
                          computedAt={computedAt}
                          livePrice={lq?.price ?? null}
                          livePulse={!!lq?.is_open && lq?.price != null}
                        />
                      );
                    })}
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
