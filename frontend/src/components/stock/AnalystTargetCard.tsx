import { ArrowDown, ArrowRight, ArrowUp, Sparkles, Target } from "lucide-react";

import type { AnalystAction, AnalystPriceTarget, AnalystRating } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { useStockFundamentals } from "@/hooks/useStockFundamentals";
import { cn } from "@/lib/utils";

interface Props {
  ticker: string;
}

/* ─── Price-target range bar ────────────────────────────────────────────── */
/* Visualizes the analyst price-target distribution as a horizontal scale:
 *
 *   $low ───●─────|───────────△──── $high
 *           ↑     ↑           ↑
 *        current mean        high
 *
 * A bar conveys the *spread* (how much analysts disagree) and where the
 * current price sits in that spread, which is more informative than the
 * three numbers alone — a current price near low + a wide range = upside,
 * current near high + tight range = limited upside.
 */
function PriceTargetBar({ pt }: { pt: AnalystPriceTarget }) {
  const { low, high, mean, median, current } = pt;
  if (low == null || high == null || mean == null || high <= low) return null;

  const span = high - low;
  // Position helper: clamps to [0,100] so out-of-range markers (e.g. current
  // price below "analyst low") still render at the edge instead of escaping.
  const pos = (v: number | null) =>
    v == null ? null : Math.max(0, Math.min(100, ((v - low) / span) * 100));

  const meanPos = pos(mean);
  const medianPos = pos(median);
  const currentPos = pos(current);

  const upside =
    current != null && current > 0 ? ((mean - current) / current) * 100 : null;

  return (
    <div className="rounded-md bg-muted/40 p-3">
      <div className="flex items-center justify-between text-[11px] uppercase tracking-wider text-muted-foreground mb-2">
        <span>Price target consensus</span>
        {upside != null && (
          <span
            className={cn(
              "font-bold tabular-nums",
              upside > 0
                ? "text-emerald-700 dark:text-emerald-300"
                : "text-rose-700 dark:text-rose-300",
            )}
            title={`Upside implicito: ${upside.toFixed(1)}% sul prezzo corrente`}
          >
            {upside >= 0 ? "+" : ""}
            {upside.toFixed(1)}%
          </span>
        )}
      </div>

      {/* Mean target as the headline number */}
      <div className="flex items-baseline gap-2 mb-3 tabular-nums">
        <span className="text-2xl font-bold">${mean.toFixed(2)}</span>
        <span className="text-[11px] text-muted-foreground">target medio</span>
      </div>

      {/* The bar itself: low → high gradient with markers stacked above. */}
      <div className="relative">
        {/* Marker labels above the bar */}
        <div className="relative h-5 mb-1 text-[10px]">
          {currentPos != null && (
            <div
              className="absolute -translate-x-1/2 flex flex-col items-center"
              style={{ left: `${currentPos}%` }}
            >
              <span className="font-semibold text-foreground/80">
                ${current!.toFixed(2)}
              </span>
              <span className="text-muted-foreground">ora</span>
            </div>
          )}
        </div>

        {/* The gradient bar */}
        <div className="relative h-2 rounded-full bg-gradient-to-r from-rose-300 via-amber-300 to-emerald-300 dark:from-rose-700 dark:via-amber-700 dark:to-emerald-700">
          {/* Mean tick (always shown) */}
          {meanPos != null && (
            <div
              className="absolute -top-1 -translate-x-1/2 h-4 w-0.5 bg-foreground"
              style={{ left: `${meanPos}%` }}
              title={`Mean: $${mean.toFixed(2)}`}
            />
          )}
          {/* Median tick (lighter, only if it differs noticeably from mean) */}
          {medianPos != null &&
            median != null &&
            Math.abs(medianPos - (meanPos ?? medianPos)) > 1 && (
              <div
                className="absolute -top-0.5 -translate-x-1/2 h-3 w-0.5 bg-foreground/40"
                style={{ left: `${medianPos}%` }}
                title={`Median: $${median.toFixed(2)}`}
              />
            )}
          {/* Current-price marker — diamond, sits on top of bar */}
          {currentPos != null && (
            <div
              className="absolute -top-1 -translate-x-1/2 h-4 w-4 rotate-45 bg-foreground border-2 border-background"
              style={{ left: `${currentPos}%` }}
              title={`Prezzo corrente: $${current!.toFixed(2)}`}
            />
          )}
        </div>

        {/* Low / high labels under the bar */}
        <div className="flex items-center justify-between mt-1.5 text-[11px] tabular-nums text-muted-foreground">
          <span title="Target più basso fra gli analisti">
            low <span className="font-semibold text-foreground/70">${low.toFixed(2)}</span>
          </span>
          <span title="Target più alto fra gli analisti">
            high <span className="font-semibold text-foreground/70">${high.toFixed(2)}</span>
          </span>
        </div>
      </div>
    </div>
  );
}

/* ─── Recommendation buy/hold/sell bar (latest snapshot only) ───────────── */

function RatingBar({ r }: { r: AnalystRating }) {
  const buy = r.strong_buy + r.buy;
  const sell = r.strong_sell + r.sell;
  const hold = r.hold;
  const total = buy + hold + sell;
  if (total === 0) return null;
  const pct = (n: number) => `${(n / total) * 100}%`;
  return (
    <div>
      <div className="flex items-center justify-between text-[11px] uppercase tracking-wider text-muted-foreground mb-1">
        <span>Recommendation</span>
        <span className="tabular-nums normal-case">{total} analisti</span>
      </div>
      <div className="flex h-2.5 rounded-full overflow-hidden bg-muted">
        <div
          className="bg-emerald-500"
          style={{ width: pct(buy) }}
          title={`Buy: ${buy} (di cui ${r.strong_buy} Strong Buy)`}
        />
        <div className="bg-amber-400" style={{ width: pct(hold) }} title={`Hold: ${hold}`} />
        <div
          className="bg-rose-500"
          style={{ width: pct(sell) }}
          title={`Sell: ${sell} (di cui ${r.strong_sell} Strong Sell)`}
        />
      </div>
      <div className="flex items-center justify-between mt-1 text-[11px] tabular-nums">
        <span className="text-emerald-700 dark:text-emerald-300 font-semibold">
          {buy} buy
        </span>
        <span className="text-amber-700 dark:text-amber-300 font-semibold">
          {hold} hold
        </span>
        <span className="text-rose-700 dark:text-rose-300 font-semibold">
          {sell} sell
        </span>
      </div>
    </div>
  );
}

/* ─── Per-analyst actions list (upgrades/downgrades/coverage init) ──────── */
/* Recent yfinance versions DO expose per-analyst price targets via
 * upgrades_downgrades — the AnalystAction type carries optional
 * current_price_target / prior_price_target / price_target_action fields.
 * When present, we render the dollar number and the prior→current arrow
 * inline alongside the rating grade so the user sees both signals at once.
 * When absent (older yfinance, missing data) the row just shows the rating.
 */

/** Map a Yahoo "ToGrade" string to a tone: buy/hold/sell. Yahoo returns
 *  a wide variety of free-form labels ("Buy", "Outperform", "Overweight",
 *  "Strong Buy", etc.) so we use substring matching on a normalized string. */
function gradeTone(grade: string): "buy" | "hold" | "sell" | "neutral" {
  const g = grade.toLowerCase();
  if (
    g.includes("buy") ||
    g.includes("outperform") ||
    g.includes("overweight") ||
    g.includes("positive") ||
    g.includes("accumulate")
  ) {
    return "buy";
  }
  if (
    g.includes("sell") ||
    g.includes("underperform") ||
    g.includes("underweight") ||
    g.includes("negative") ||
    g.includes("reduce")
  ) {
    return "sell";
  }
  if (g.includes("hold") || g.includes("neutral") || g.includes("equal") || g.includes("market perform")) {
    return "hold";
  }
  return "neutral";
}

const TONE_CLASSES: Record<ReturnType<typeof gradeTone>, string> = {
  buy: "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-800 dark:text-emerald-200",
  hold: "bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200",
  sell: "bg-rose-100 dark:bg-rose-900/40 text-rose-800 dark:text-rose-200",
  neutral: "bg-muted text-muted-foreground",
};

/** Action arrows: Yahoo's "action" field is a short code:
 *   "up" = upgrade, "down" = downgrade, "init" = coverage initiated,
 *   "main"/"reit" = maintained/reiterated. */
function actionIcon(action: string) {
  const a = action.toLowerCase();
  if (a === "up" || a === "upgrade") {
    return <ArrowUp className="h-3 w-3 text-emerald-600 dark:text-emerald-400 shrink-0" />;
  }
  if (a === "down" || a === "downgrade") {
    return <ArrowDown className="h-3 w-3 text-rose-600 dark:text-rose-400 shrink-0" />;
  }
  if (a === "init") {
    return <Sparkles className="h-3 w-3 text-blue-600 dark:text-blue-400 shrink-0" />;
  }
  // main / reit / unknown
  return <ArrowRight className="h-3 w-3 text-muted-foreground shrink-0" />;
}

/** Format YYYY-MM-DD as e.g. "4 mag" (locale-aware short). */
function fmtShortDate(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("it-IT", { day: "numeric", month: "short" });
}

/** Format a price-target action ("Raises" / "Lowers" / "Maintains" /
 *  "Initiates") into a tone-classed mini-arrow + label pair. We use the
 *  yfinance label rather than infer direction from current vs prior numbers
 *  because the label disambiguates the "Initiates" case (no prior value)
 *  and matches the source-of-truth labeling. */
function priceTargetTone(action: string | null | undefined): {
  cls: string;
  arrow: string;
} {
  switch (action) {
    case "Raises":
      return { cls: "text-emerald-700 dark:text-emerald-300", arrow: "↑" };
    case "Lowers":
      return { cls: "text-rose-700 dark:text-rose-300", arrow: "↓" };
    case "Initiates":
      return { cls: "text-blue-700 dark:text-blue-300", arrow: "✦" };
    case "Maintains":
    default:
      return { cls: "text-muted-foreground", arrow: "→" };
  }
}

/** Compact price-target chip: shows the new dollar number + a tone-colored
 *  arrow indicating the direction of the change. The full prior→current
 *  detail moves to the row's hover tooltip — single-line layout doesn't
 *  have horizontal budget for both numbers, so we surface the most
 *  important value (new target) and the direction signal (↑/↓/=/✦). */
function PriceTargetChip({ a }: { a: AnalystAction }) {
  const hasTarget = a.current_price_target != null && Number.isFinite(a.current_price_target);
  if (!hasTarget) return null;
  const ptTone = priceTargetTone(a.price_target_action);
  const target = a.current_price_target!;
  // Drop cents when the target is a round number to save 3 chars of width
  // — yfinance's analyst targets are almost always whole-dollar values
  // (e.g. $296, $350) so this almost always trims.
  const fmt = Number.isInteger(target) ? `$${target}` : `$${target.toFixed(2)}`;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 tabular-nums font-bold shrink-0",
        ptTone.cls,
      )}
    >
      <span className="text-[11px]">{ptTone.arrow}</span>
      <span>{fmt}</span>
    </span>
  );
}

function ActionsList({ actions }: { actions: AnalystAction[] }) {
  if (actions.length === 0) {
    return (
      <div className="text-[11px] text-muted-foreground italic px-1 py-2">
        Nessuna azione recente di analisti disponibile.
      </div>
    );
  }
  return (
    <ul className="space-y-1">
      {actions.map((a, i) => {
        const tone = gradeTone(a.to_grade);
        const hasTarget = a.current_price_target != null && Number.isFinite(a.current_price_target);
        const hasPrior = a.prior_price_target != null && Number.isFinite(a.prior_price_target);
        // Rich tooltip text — single-line layout can't show prior→current
        // detail inline, so the full transition lives on hover.
        const tooltipParts = [
          `${a.firm}: ${a.from_grade || "—"} → ${a.to_grade} (${a.action})`,
        ];
        if (hasTarget) {
          if (hasPrior) {
            tooltipParts.push(
              `Target ${a.price_target_action ?? "—"}: $${a.prior_price_target!.toFixed(2)} → $${a.current_price_target!.toFixed(2)}`,
            );
          } else {
            tooltipParts.push(
              `Target ${a.price_target_action ?? "—"}: $${a.current_price_target!.toFixed(2)}`,
            );
          }
        }

        return (
          <li
            key={`${a.date}-${a.firm}-${i}`}
            className="flex items-center gap-1.5 text-[11px] py-1 border-b border-border/40 last:border-b-0"
            title={tooltipParts.join("\n")}
          >
            {actionIcon(a.action)}
            {/* Firm: shrinks first when the row gets tight. min-w-0 is
                required for `truncate` to work inside a flex item. */}
            <span className="font-semibold truncate flex-1 min-w-0" title={a.firm}>
              {a.firm}
            </span>
            {/* Grade chip — buy/hold/sell tone */}
            <span
              className={cn(
                "px-1.5 py-0.5 rounded font-semibold shrink-0",
                TONE_CLASSES[tone],
              )}
            >
              {a.to_grade || "—"}
            </span>
            {/* Price target chip — directly adjacent to the grade so they
                read as a "rating + target" unit. Renders only when the
                API gave us a target. */}
            <PriceTargetChip a={a} />
            <span className="text-muted-foreground tabular-nums shrink-0 w-10 text-right">
              {fmtShortDate(a.date)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/* ─── Card root ─────────────────────────────────────────────────────────── */

/**
 * Analyst price-target + recommendation + per-analyst actions.
 * Sits next to StockHeader at the top of the page so the consensus is
 * visible as soon as the page loads.
 *
 * Layout (top to bottom):
 *   1. Price-target range bar (low / mean / median / high + current marker)
 *   2. Buy/hold/sell distribution bar (latest snapshot)
 *   3. Scrollable list of upgrades/downgrades/initiations
 */
export function AnalystTargetCard({ ticker }: Props) {
  const q = useStockFundamentals(ticker);

  if (q.isLoading) {
    return (
      <Card className="h-full">
        <CardContent className="p-4 h-full flex flex-col">
          <div className="flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            <Target className="h-4 w-4" /> Analyst
          </div>
          <div className="flex-1 animate-pulse bg-muted/40 rounded" />
        </CardContent>
      </Card>
    );
  }

  const f = q.data;
  const pt = f?.price_target ?? null;
  const ratings = f?.analyst_ratings ?? [];
  const actions = f?.analyst_actions ?? [];
  const hasPT = pt && pt.mean != null && pt.low != null && pt.high != null;
  const hasRatings = ratings.length > 0;
  const hasActions = actions.length > 0;

  if (!hasPT && !hasRatings && !hasActions) {
    return (
      <Card className="h-full">
        <CardContent className="p-4 h-full flex flex-col">
          <div className="flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            <Target className="h-4 w-4" /> Analyst
          </div>
          <div className="flex-1 flex items-center justify-center text-[11px] text-muted-foreground text-center px-2">
            Nessuna stima analista disponibile.
          </div>
        </CardContent>
      </Card>
    );
  }

  // Latest rating row (period === "0m" is the current snapshot)
  const latest = ratings.find((r) => r.period === "0m") ?? ratings[0];

  return (
    <Card className="h-full overflow-hidden">
      {/* gap-2 + min-h-0 + the inner overflow-y-auto on the actions list make
          this card resilient: the price-target bar and ratings bar are fixed
          (shrink-0), only the actions list scrolls when there are many rows. */}
      <CardContent className="p-4 h-full flex flex-col gap-2 min-h-0">
        <div className="flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wide text-muted-foreground shrink-0">
          <Target className="h-4 w-4" /> Analyst
        </div>

        {hasPT && pt && (
          <div className="shrink-0">
            <PriceTargetBar pt={pt} />
          </div>
        )}

        {hasRatings && latest && (
          <div className="shrink-0">
            <RatingBar r={latest} />
          </div>
        )}

        {/* Actions list — capped at ~5 visible rows then scrolls internally.
            max-h: 180px ≈ 5-6 single-line rows (each ~28px = py-1 + content
            + border). Halved from the previous 320px since rows compacted
            from 2 lines to 1 with the price target moved inline. Fixed
            cap (vs flex-1) keeps the card compact regardless of action
            count and gives the user a consistent visible window. */}
        <div className="flex flex-col min-h-0">
          <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1 shrink-0 flex items-center justify-between">
            <span>Azioni recenti</span>
            {actions.length > 0 && (
              <span className="tabular-nums normal-case text-muted-foreground/70">
                {actions.length} totali
              </span>
            )}
          </div>
          <div className="overflow-y-auto pr-1 max-h-[180px]">
            <ActionsList actions={actions} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
