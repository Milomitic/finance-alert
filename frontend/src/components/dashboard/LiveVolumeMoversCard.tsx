import { Activity, Radio } from "lucide-react";
import { Link } from "react-router-dom";
import { useMemo } from "react";

import type { MoversBlock } from "@/api/types";
import { StockIdentity } from "@/components/dashboard/StockIdentity";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useLiveQuotes } from "@/hooks/useLiveQuote";
import { cn } from "@/lib/utils";

interface Props {
  movers: MoversBlock;
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
export function LiveVolumeMoversCard({ movers }: Props) {
  const ROWS_VISIBLE = 10;
  // Use the new `top_volume` list (ranked by absolute share-volume).
  // Falls back to the legacy `volume_spikes` (ranked by ratio) when
  // the snapshot pre-dates the field, so older snapshots still
  // render something useful instead of an empty card.
  const sourceRows = (movers.top_volume?.length ?? 0) > 0
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
        is_open: q.market_state === "OPEN",
      });
    }
    return m;
  }, [liveQ.data]);

  const anyMarketOpen = useMemo(
    () => Array.from(liveByTicker.values()).some((v) => v.is_open),
    [liveByTicker],
  );

  return (
    <Card className="h-full overflow-hidden">
      <CardContent className="p-0 flex flex-col h-full min-h-0">
        <div className="px-3 py-2 border-b bg-muted/30 shrink-0">
          <SectionTitle
            icon={Activity}
            label="Volumi maggiori oggi"
            right={
              anyMarketOpen ? (
                <span
                  className="inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider text-emerald-700 dark:text-emerald-300"
                  title="Almeno un mercato è aperto — prezzi in live update ogni 15s"
                >
                  <span className="relative inline-flex h-1.5 w-1.5">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
                  </span>
                  <Radio className="h-2.5 w-2.5" />
                  LIVE
                </span>
              ) : (
                <span
                  className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground"
                  title="Tutti i mercati visibili sono chiusi — mostro l'ultima chiusura disponibile"
                >
                  Closed
                </span>
              )
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
              const volRatio =
                "vol_ratio" in r ? (r as { vol_ratio?: number | null }).vol_ratio ?? null : null;
              const composite =
                "composite" in r
                  ? (r as { composite?: number | null }).composite ?? null
                  : null;
              return (
                <li key={r.ticker}>
                  <Link
                    to={`/stocks/${encodeURIComponent(r.ticker)}`}
                    className="grid grid-cols-[minmax(0,1fr)_auto_auto] sm:grid-cols-[minmax(0,1fr)_auto_auto_auto_auto_auto] items-center gap-2 px-3 py-1.5 hover:bg-accent/30 transition-colors"
                  >
                    {/* Col 1: identity + inline %change ("how is it moving") */}
                    <div className="flex items-center gap-2 min-w-0">
                      <StockIdentity ticker={r.ticker} name={r.name} />
                      <span
                        className={cn(
                          "shrink-0 text-[11px] font-semibold tabular-nums",
                          displayChange != null && displayChange >= 0
                            ? "text-emerald-600 dark:text-emerald-400"
                            : displayChange != null
                              ? "text-rose-600 dark:text-rose-400"
                              : "text-muted-foreground",
                        )}
                        title="Variazione % giornaliera (live)"
                      >
                        {displayChange != null
                          ? `${displayChange >= 0 ? "+" : ""}${displayChange.toFixed(2)}%`
                          : "—"}
                      </span>
                    </div>

                    {/* Col 2: live price */}
                    <div
                      className={cn(
                        "shrink-0 text-sm font-semibold tabular-nums",
                        livePulse && "underline decoration-dotted decoration-emerald-500/60 underline-offset-2",
                      )}
                      title={
                        livePulse ? "Prezzo live (polling 15s)" : "Ultima chiusura disponibile"
                      }
                    >
                      {displayPrice != null ? `$${displayPrice.toFixed(2)}` : "—"}
                    </div>

                    {/* Col 3: absolute volume — the actual ranking
                        criterion. Formatted as compact 12.4M / 1.2B.
                        Bumped from text-[11px] to text-sm with a wider
                        column so the figure stays comfortably readable
                        at typical viewport widths. */}
                    <div
                      className="hidden sm:block shrink-0 text-sm font-semibold tabular-nums text-foreground/80 min-w-[68px] text-right"
                      title={
                        volToday != null
                          ? `${volToday.toLocaleString("it-IT")} share scambiate oggi`
                          : undefined
                      }
                    >
                      {fmtVolume(volToday)}
                    </div>

                    {/* Col 4: vol multiplier (vs 20-day avg). Orange
                        tint at ≥3× signals "really unusual". Bumped
                        text-[10px] → text-xs and wider min-w so the
                        chip reads at a glance like the score on its
                        right. */}
                    <div
                      className={cn(
                        "hidden sm:block shrink-0 text-xs font-mono font-semibold tabular-nums rounded px-2 py-0.5 min-w-[52px] text-center",
                        volRatio != null && volRatio >= 3
                          ? "bg-orange-100 dark:bg-orange-950/40 text-orange-800 dark:text-orange-200"
                          : volRatio != null && volRatio >= 2
                            ? "bg-muted/70 text-foreground/80"
                            : "text-muted-foreground/70",
                      )}
                      title={
                        volRatio != null
                          ? `Volume oggi ${volRatio.toFixed(2)}× la media a 20 giorni`
                          : "Multiplo vs media a 20 giorni non disponibile"
                      }
                    >
                      {volRatio != null ? `${volRatio.toFixed(1)}×` : "—"}
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
 *  number; null is rendered as em-dash. */
function fmtVolume(v: number | null): string {
  if (v == null || !Number.isFinite(v)) return "—";
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}k`;
  return v.toString();
}

/** Composite score chip — color-coded by tier so the card shows
 *  "high-volume + high-score" at a glance.
 *  Tailwind purger needs literal class strings; keep this as a switch,
 *  not a template. */
function ScoreChip({ score }: { score: number | null | undefined }) {
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
