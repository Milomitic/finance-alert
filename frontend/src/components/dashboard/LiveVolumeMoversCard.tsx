import { Activity } from "lucide-react";
import { Link } from "react-router-dom";
import { useMemo, useState } from "react";

import type { MoversBlock } from "@/api/types";
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
import { projectVolRatio } from "@/lib/intradayVolume";
import { cn } from "@/lib/utils";

type VolMode = "dollar" | "shares";

interface Props {
  movers: MoversBlock;
  /** Market snapshot `computed_at` — used as time reference for the
   *  intraday vol_ratio projection (see `projectVolRatio`). */
  computedAt?: string | null;
}

/* ─── LiveVolumeMoversCard ────────────────────────────────────────────────
 *
 * Companion to the BreadthMatrixTable on row 2 of the dashboard. Mirrors
 * the HeroStrip's two-column pattern (`[3fr_2fr]`): breadth table left,
 * this live-volume card right.
 *
 * Ranks the most actively-traded stocks of the day by ABSOLUTE share
 * volume (e.g. "112M shares"), with live prices polled at 15s cadence.
 * Each row carries five things in tight columns:
 *
 *   ┌──────────────────────────────────────────────────────────────────┐
 *   │  ◇ NVDA  Nvidia        +2.18%   $142.30   112M  3.2×    78  ✓   │
 *   │  ◇ TSLA  Tesla         −1.04%   $245.10    87M  2.8×    62      │
 *   │  ◇ AAPL  Apple         +0.30%   $234.50    76M  1.4×    71      │
 *   │   ticker+name + %chg   price    vol    ratio  score          │
 *   └──────────────────────────────────────────────────────────────────┘
 *
 * Data:
 *   - `movers.top_volume`: from /api/dashboard/market-summary, sorted by
 *     vol_today desc, scan-time snapshot. Carries vol_today,
 *     vol_ratio, and the latest persisted composite score.
 *   - Live overlay: `useLiveQuotes` batch poll refreshes price +
 *     change_pct every 15s. Falls back to the snapshot's last_close +
 *     change_pct when live is unavailable.
 *
 * Layout rationale (per user request):
 *   - % change RIGHT NEXT TO the ticker/name — it's the headline
 *     "how is this thing moving" signal.
 *   - Score on the RIGHT-MOST column — the "is this hot or junk?"
 *     verdict. Color-coded by tier.
 *   - Multiplier (vol_ratio) kept but demoted to a small chip between
 *     volume and score — secondary context ("how unusual is this
 *     volume vs typical?").
 *   - Absolute volume is the actual ranking criterion — sits where
 *     the eye scans naturally between price and score.
 */
export function LiveVolumeMoversCard({ movers, computedAt }: Props) {
  const ROWS_VISIBLE = 10;
  // Default to DOLLAR (notional) turnover — "where the money flowed".
  // Raw share-count over-represents cheap instruments (inverse leveraged
  // ETFs like SOXS/TZA trade huge share counts at a few dollars while
  // their high-priced bull twins SOXL/TNA move far more dollars on fewer
  // shares), so the share view alone is misleading. The toggle keeps both.
  const [mode, setMode] = useState<VolMode>("dollar");

  // Show dollar ranking only when the backend actually provided the
  // dollar-ranked list (older snapshots predate it) — otherwise fall
  // back to the share view so the figure and the ordering stay consistent.
  const hasDollar = (movers.top_dollar_volume?.length ?? 0) > 0;
  const showDollar = mode === "dollar" && hasDollar;

  // Source list per view. Dollar → top_dollar_volume; shares → the
  // share-ranked top_volume (legacy volume_spikes fallback for very old
  // snapshots so the card still renders something).
  const sourceRows = showDollar
    ? movers.top_dollar_volume!
    : (movers.top_volume?.length ?? 0) > 0
      ? movers.top_volume!
      : (movers.volume_spikes ?? []);
  const rows = sourceRows.slice(0, ROWS_VISIBLE);
  const tickers = useMemo(() => rows.map((r) => r.ticker), [rows]);
  const liveQ = useLiveQuotes(tickers, tickers.length > 0);
  const liveByTicker = useMemo(() => {
    const m = new Map<string, { price: number | null; change_pct: number | null; is_open: boolean }>();
    for (const q of liveQ.data?.quotes ?? []) {
      m.set(q.ticker, {
        price: q.price ?? null,
        change_pct: q.change_pct ?? null,
        // OPEN and PRE both carry a fresh live/pre-market price → pulse.
        is_open: q.market_state === "OPEN" || q.market_state === "PRE",
      });
    }
    return m;
  }, [liveQ.data]);

  // Aggregate phase across the polled tickers → drives the LIVE/PRE/Closed
  // badge so the user knows whether the % is regular-session, pre-market,
  // or last EOD close.
  const phase = useMemo(
    () => deriveMarketPhase((liveQ.data?.quotes ?? []).map((q) => q.market_state)),
    [liveQ.data],
  );

  return (
    <Card className="h-full overflow-hidden">
      <CardContent className="p-0 flex flex-col h-full min-h-0">
        <div className="px-3 py-2 border-b bg-muted/30 shrink-0">
          <SectionTitle
            icon={Activity}
            label="Volumi maggiori oggi"
            right={
              <div className="flex items-center gap-2">
                <MarketStateBadge phase={phase} />
                <Tabs value={mode} onValueChange={(v) => setMode(v as VolMode)}>
                  <TabsList className="h-6 p-0.5">
                    <TabsTrigger
                      value="dollar"
                      className="h-5 text-[10px] px-1.5"
                      title="Ordina per controvalore scambiato (volume × prezzo, convertito in USD) — la vera dimensione del flusso di denaro"
                    >
                      $
                    </TabsTrigger>
                    <TabsTrigger
                      value="shares"
                      className="h-5 text-[10px] px-1.5"
                      title="Ordina per numero di azioni scambiate (favorisce i titoli a basso prezzo)"
                    >
                      Vol
                    </TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>
            }
          />
        </div>

        {rows.length === 0 ? (
          <div className="flex-1 flex items-center justify-center p-4 text-xs text-muted-foreground">
            Nessun dato di volume per oggi.
          </div>
        ) : (
          <ul className="flex-1 overflow-y-auto divide-y divide-border/40">
            {rows.map((r) => {
              const live = liveByTicker.get(r.ticker);
              const displayPrice = live?.price ?? r.last_close ?? null;
              const displayChange = live?.change_pct ?? r.change_pct ?? null;
              const livePulse = !!live?.is_open && live?.price != null;
              // Both `top_volume` and `volume_spikes` rows carry these
              // (when using the new list). `volume_spikes` fallback has
              // vol_ratio but no vol_today — handle both shapes.
              const volToday =
                "vol_today" in r ? (r as { vol_today?: number }).vol_today ?? null : null;
              const dollarVol =
                "dollar_volume" in r
                  ? (r as { dollar_volume?: number | null }).dollar_volume ?? null
                  : null;
              const rawVolRatio =
                "vol_ratio" in r ? (r as { vol_ratio?: number | null }).vol_ratio ?? null : null;
              // Project to end-of-day using the intraday cum-volume
              // curve. Outside US session (or in the first 30 min)
              // the helper returns `projected:false` and we display
              // the raw ratio unchanged.
              const projVol = projectVolRatio(rawVolRatio, computedAt);
              const volRatio = projVol?.value ?? null;
              const isProjected = !!projVol?.projected;
              const composite =
                "composite" in r
                  ? (r as { composite?: number | null }).composite ?? null
                  : null;
              return (
                <li key={r.ticker}>
                  <Link
                    to={`/stocks/${encodeURIComponent(r.ticker)}`}
                    className="grid grid-cols-[minmax(0,1fr)_auto_auto_auto] sm:grid-cols-[minmax(0,1fr)_auto_auto_auto_auto_auto] items-center gap-2 px-3 py-1.5 hover:bg-accent/30 transition-colors"
                  >
                    {/* Col 1: identity + per-row live-poll dot.
                        Previously the "is this row being polled
                        live?" signal was a dotted-underline on the
                        PRICE (only visible on hover). The user asked
                        to surface it explicitly: a classic pulsing
                        green dot sits IMMEDIATELY right of the
                        ticker, visible at a glance for every row
                        whose 15s polling is currently active. */}
                    <div className="flex items-center gap-2 min-w-0">
                      <StockIdentity ticker={r.ticker} name={r.name} />
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

                    {/* Col 2: price — underline removed; live state
                        now communicated by the green dot above.
                        Wrapped in FlashValue for the Wall-Street-tape
                        tint (emerald uptick / rose downtick) on each
                        15s polling refresh. `noTween` avoids running
                        N simultaneous number-tweens on a 10-row list. */}
                    <div
                      className="shrink-0 text-sm font-semibold tabular-nums"
                      title={
                        livePulse ? "Prezzo live (polling 15s)" : "Ultima chiusura disponibile"
                      }
                    >
                      <FlashValue
                        value={displayPrice}
                        format={(p) => `$${p.toFixed(2)}`}
                        noTween
                      />
                    </div>

                    {/* Col 3: %change — to the RIGHT of the price, a
                        notch larger than before (13px) for emphasis.
                        Also flash-tinted on live ticks: the base
                        green/red sign-color is the steady state, the
                        flash briefly overrides during the ~700ms
                        transition window (a downtick on a positive %
                        flashes rose then settles back to green —
                        classic NYSE tape behavior). */}
                    <span
                      className={cn(
                        "shrink-0 text-[13px] font-semibold tabular-nums w-[62px] text-right",
                        displayChange != null && displayChange >= 0
                          ? "text-emerald-600 dark:text-emerald-400"
                          : displayChange != null
                            ? "text-rose-600 dark:text-rose-400"
                            : "text-muted-foreground",
                      )}
                      title="Variazione % giornaliera (live)"
                    >
                      <FlashValue
                        value={displayChange}
                        format={(p) => `${p >= 0 ? "+" : ""}${p.toFixed(2)}%`}
                        noTween
                      />
                    </span>

                    {/* Col 3: the ranking criterion. In "$" mode it's the
                        USD notional turnover ("$9.2B" — where the money
                        flowed); in "Vol" mode it's the raw share count
                        ("250M"). The tooltip always shows BOTH so the
                        cross-reference is one hover away. */}
                    <div
                      className="hidden sm:block shrink-0 text-sm font-semibold tabular-nums text-foreground/80 min-w-[68px] text-right"
                      title={
                        [
                          dollarVol != null
                            ? `Controvalore ≈ $${Math.round(dollarVol).toLocaleString("it-IT")}`
                            : null,
                          volToday != null
                            ? `${volToday.toLocaleString("it-IT")} share scambiate oggi`
                            : null,
                        ]
                          .filter(Boolean)
                          .join(" · ") || undefined
                      }
                    >
                      {showDollar ? fmtDollar(dollarVol) : fmtVolume(volToday)}
                    </div>

                    {/* Col 4: vol multiplier (vs 20-day avg).
                        INTRADAY-PROJECTED to end-of-day when the
                        snapshot is partial (see `projectVolRatio`).
                        A "~" prefix marks projected values so the
                        user reads them as estimates. Orange tint at
                        ≥3× still signals "really unusual" — applied
                        to the projected figure since that's the one
                        that reflects the burst regardless of when
                        in the session we're looking. */}
                    <div
                      className={cn(
                        "hidden sm:block shrink-0 text-xs font-mono font-semibold tabular-nums rounded px-2 py-0.5 min-w-[56px] text-center",
                        volRatio != null && volRatio >= 3
                          ? "bg-orange-100 dark:bg-orange-950/40 text-orange-800 dark:text-orange-200"
                          : volRatio != null && volRatio >= 2
                            ? "bg-muted/70 text-foreground/80"
                            : "text-muted-foreground/70",
                      )}
                      title={
                        volRatio != null
                          ? isProjected
                            ? `Proiezione fine giornata ~${volRatio.toFixed(2)}× (scalato dalla curva intraday a ${Math.round((projVol?.fraction ?? 0) * 100)}% sessione)`
                            : `Volume oggi ${volRatio.toFixed(2)}× la media a 20 giorni`
                          : "Multiplo vs media a 20 giorni non disponibile"
                      }
                    >
                      {volRatio != null
                        ? `${isProjected ? "~" : ""}${volRatio.toFixed(1)}×`
                        : "—"}
                    </div>

                    {/* Col 5: composite score (latest persisted). Color
                        tier matches the rest of the dashboard. */}
                    <ScoreChip score={composite} />
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

/** Render absolute share volume as compact "12.4M" / "1.2B" — keeps
 *  the column narrow while still readable. Below 1k shows the raw
 *  number; null is rendered as em-dash.
 *  Exported so the sibling TopMoversCard (which now also surfaces
 *  volume next to the % change) can share the same vocabulary. */
export function fmtVolume(v: number | null): string {
  if (v == null || !Number.isFinite(v)) return "—";
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}k`;
  return v.toString();
}

/** Render USD notional turnover as compact "$9.2B" / "$340M". Mirrors
 *  fmtVolume but money-prefixed and with a T tier (whole-market days).
 *  null → em-dash. */
export function fmtDollar(v: number | null): string {
  if (v == null || !Number.isFinite(v)) return "—";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}k`;
  return `$${v.toFixed(0)}`;
}

/** Composite score chip — color-coded by tier so the card shows
 *  "high-volume + high-score" at a glance.
 *  Tailwind purger needs literal class strings; keep this as a switch,
 *  not a template.
 *  Exported so the sibling TopMoversCard can render the same chip in
 *  its gainers/losers rows — keeps the visual vocabulary consistent
 *  ("a score is a score is a score" across the dashboard). */
export function ScoreChip({ score }: { score: number | null | undefined }) {
  if (score == null || !Number.isFinite(score)) {
    return (
      <span
        className="shrink-0 text-xs tabular-nums rounded px-2 py-0.5 min-w-[44px] text-center text-muted-foreground/60"
        title="Score non ancora calcolato"
      >
        —
      </span>
    );
  }
  const cls =
    score >= 70
      ? "bg-emerald-100 dark:bg-emerald-950/40 text-emerald-800 dark:text-emerald-200"
      : score >= 50
        ? "bg-sky-100 dark:bg-sky-950/40 text-sky-800 dark:text-sky-200"
        : score >= 30
          ? "bg-amber-100 dark:bg-amber-950/40 text-amber-800 dark:text-amber-200"
          : "bg-rose-100 dark:bg-rose-950/40 text-rose-800 dark:text-rose-200";
  return (
    <span
      className={cn(
        // Bumped from text-[11px] / px-1.5 / min-w-28 to text-sm /
        // px-2 / min-w-44 so the score chip reads at the same weight
        // as the price column to its left. Same visual treatment as
        // the BreadthMatrixTable's score column.
        "shrink-0 text-sm font-semibold tabular-nums rounded px-2 py-0.5 min-w-[44px] text-center",
        cls,
      )}
      title={`Score composito ${score.toFixed(0)}/100`}
    >
      {score.toFixed(0)}
    </span>
  );
}
