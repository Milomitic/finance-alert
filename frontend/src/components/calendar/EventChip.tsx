import { Link } from "react-router-dom";

import type { CalendarEvent, EarningsEvent, MacroEvent } from "@/api/types";
import { StockLogo } from "@/components/dashboard/StockLogo";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  IMPORTANCE_BG,
  IMPORTANCE_LABEL,
  earningsBeatTone,
  formatEps,
  formatMarketCap,
  regionFlag,
  regionFlagAsset,
  regionLabel,
} from "@/lib/calendarMeta";
import { getSectorRing, getSectorTone } from "@/lib/sectorMeta";
import { cn } from "@/lib/utils";

import { ImportanceDots } from "./ImportanceDots";

/* ─── EventChip — discriminated dispatcher ──────────────────────────────── */
/* The chip is the page's most-rendered element (potentially 100+ on a
 * dense month). Keep the markup lean: one outer pill/stamp, hover ring,
 * Tooltip wrapper. The two kinds have distinct silhouettes:
 *   - earnings → fully rounded pill with logo + ticker (organic shape)
 *   - macro    → sharper rectangle with a saturated left ribbon
 *                (stamp/passport feel)
 *
 * Both share the same height (h-6) so adjacent chips align in a tidy
 * vertical stack. Different shapes + different palettes mean the user
 * never has to read text to tell them apart. */

interface EventChipProps {
  event: CalendarEvent;
  /** When inside a day cell we don't want every chip stealing focus on
   *  Tab — the cell button is the keyboard-reachable element. Setting
   *  `tabIndex=-1` keeps the chips out of the tab order while still
   *  keeping click + hover behavior. */
  tabIndex?: number;
  /** Pass-through for clicks bubbling up to the parent cell — used to
   *  let the cell handle the day-detail open while still letting the
   *  ticker chip navigate to the stock page. */
  onClick?: (e: React.MouseEvent) => void;
}

export function EventChip({ event, tabIndex = -1, onClick }: EventChipProps) {
  if (event.kind === "earnings") {
    return <EarningsChip event={event} tabIndex={tabIndex} onClick={onClick} />;
  }
  return <MacroChip event={event} tabIndex={tabIndex} onClick={onClick} />;
}

/* ─── Earnings chip ─────────────────────────────────────────────────────── */

function EarningsChip({
  event,
  tabIndex,
  onClick,
}: {
  event: EarningsEvent;
  tabIndex?: number;
  onClick?: (e: React.MouseEvent) => void;
}) {
  // Once the quarter has reported (surprise_pct != null) we recolor the
  // WHOLE chip green (beat) / red (miss) so the ticker label reads its
  // result at a glance; before that it keeps the neutral sector tone.
  const beatTone = earningsBeatTone(event.surprise_pct);
  const reported = beatTone != null;
  const beat = reported && (event.surprise_pct ?? 0) >= 0;
  const tone = beatTone ?? getSectorTone(event.sector);
  const ring = getSectorRing(event.sector);
  const epsLabel = formatEps(event.eps_estimate);
  const mcapLabel = formatMarketCap(event.market_cap);

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          to={`/stocks/${encodeURIComponent(event.ticker)}`}
          onClick={(e) => {
            // Stop the click from bubbling up to the day-cell button so
            // navigation goes straight to the stock page rather than also
            // popping the day-detail panel.
            e.stopPropagation();
            onClick?.(e);
          }}
          tabIndex={tabIndex}
          className={cn(
            // Pill silhouette — fully rounded, dense, with logo on the left
            "group/chip relative flex h-6 items-center gap-1.5 rounded-full border pl-0.5 pr-2",
            // Hairline border + tone fill
            tone,
            // Hover lift: subtle ring grows on hover, color taken from sector hue
            "ring-0 hover:ring-2 transition-shadow duration-150",
            ring,
            // Block-level so chips stack tidy in a flex-col
            "max-w-full overflow-hidden",
          )}
          aria-label={`Earnings ${event.ticker} ${event.name}`}
        >
          {/* Logo — small, circular, sits inside the rounded pill flush */}
          <span className="shrink-0 -ml-px">
            <StockLogo ticker={event.ticker} size="xs" />
          </span>
          <span className="text-[14px] font-bold tracking-tight tabular-nums leading-none truncate">
            {event.ticker}
          </span>
          {/* Beat/miss arrow once reported — color inherits the chip's
              green/red tone, so it reads without extra palette. */}
          {reported && (
            <span
              className="text-[11px] font-bold leading-none shrink-0"
              aria-label={beat ? "ha battuto le stime" : "sotto le stime"}
              title={beat ? "Ha battuto le stime" : "Sotto le stime"}
            >
              {beat ? "▲" : "▼"}
            </span>
          )}
          {/* V3.4: pre/after-market icon. ☀ before market open (the
              earnings was reported in pre-market window),
              ☾ after-market close. Backend infers from yfinance UTC
              timestamps vs the US session boundaries. */}
          {event.earnings_when === "pre" && (
            <span
              className="text-[11px] leading-none shrink-0"
              title="Pre-market: earnings rilasciati prima dell'apertura della sessione"
              aria-label="pre-market"
            >
              ☀
            </span>
          )}
          {event.earnings_when === "after" && (
            <span
              className="text-[11px] leading-none shrink-0 opacity-80"
              title="After-market: earnings rilasciati dopo la chiusura della sessione"
              aria-label="after-market"
            >
              ☾
            </span>
          )}
        </Link>
      </TooltipTrigger>
      <TooltipContent side="top" className="space-y-1">
        <div className="flex items-center gap-2">
          <StockLogo ticker={event.ticker} size="xs" />
          <div>
            <div className="text-base font-semibold leading-tight">
              {event.name}
            </div>
            <div className="text-[14px] text-muted-foreground tabular-nums tracking-wide">
              {event.ticker}
              {event.sector ? ` · ${event.sector}` : ""}
            </div>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 pt-1 text-[14px] tabular-nums">
          <span className="text-muted-foreground">EPS est.</span>
          <span className="text-right font-semibold">{epsLabel}</span>
          {reported && (
            <>
              <span className="text-muted-foreground">EPS rilasciato</span>
              <span
                className={cn(
                  "text-right font-semibold",
                  beat
                    ? "text-emerald-700 dark:text-emerald-300"
                    : "text-rose-700 dark:text-rose-300",
                )}
              >
                {formatEps(event.eps_reported)}
              </span>
              <span className="text-muted-foreground">Sorpresa</span>
              <span
                className={cn(
                  "text-right font-semibold",
                  beat
                    ? "text-emerald-700 dark:text-emerald-300"
                    : "text-rose-700 dark:text-rose-300",
                )}
              >
                {(event.surprise_pct ?? 0) >= 0 ? "+" : ""}
                {(event.surprise_pct ?? 0).toFixed(1)}%
              </span>
            </>
          )}
          <span className="text-muted-foreground">Cap. mercato</span>
          <span className="text-right font-semibold">{mcapLabel}</span>
        </div>
      </TooltipContent>
    </Tooltip>
  );
}

/* ─── Macro chip ────────────────────────────────────────────────────────── */

function MacroChip({
  event,
  tabIndex,
  onClick,
}: {
  event: MacroEvent;
  tabIndex?: number;
  onClick?: (e: React.MouseEvent) => void;
}) {
  const tone = IMPORTANCE_BG[event.importance];
  const flagAsset = regionFlagAsset(event.region);

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={(e) => {
            // Macro chips don't navigate — let the click bubble up to the
            // day-cell which opens the detail panel. We just stop the
            // default focus shift by not calling preventDefault.
            onClick?.(e);
          }}
          tabIndex={tabIndex}
          className={cn(
            // Stamp silhouette: sharper corners (rounded-sm), fixed height.
            // The previous left-ribbon was replaced with leading importance
            // dots — the dot count IS the importance signal now.
            "group/chip relative flex h-6 items-center gap-1 overflow-hidden rounded-sm border pl-1.5 pr-1.5 text-left",
            tone,
            // Hover ring tinted by importance — keep subtle so the chip
            // doesn't compete with the today-cell halo
            "transition-shadow duration-150 hover:shadow-sm",
            "max-w-full",
          )}
          aria-label={`${event.label} (importanza ${IMPORTANCE_LABEL[event.importance].toLowerCase()})`}
        >
          {/* Importance dots — replaces the old saturated ribbon. 1/2/3 dots
              filled tells the user the tier without color literacy. */}
          <ImportanceDots
            importance={event.importance}
            size="h-1.5 w-1.5"
            gap="gap-0.5"
            className="shrink-0"
          />
          {flagAsset ? (
            <img
              src={`/flags/${flagAsset}.svg`}
              alt={event.region ?? ""}
              width={14}
              height={10}
              style={{ width: "14px", height: "10px", objectFit: "cover" }}
              className="rounded-[1px] ring-1 ring-black/10 dark:ring-white/10 shrink-0"
              aria-hidden
            />
          ) : (
            <span className="text-[14px] leading-none shrink-0" aria-hidden>
              {regionFlag(event.region)}
            </span>
          )}
          <span className="text-[14px] font-medium leading-none truncate">
            {event.label}
          </span>
        </button>
      </TooltipTrigger>
      <TooltipContent side="top" className="space-y-1">
        <div className="flex items-baseline gap-2">
          {flagAsset ? (
            <img
              src={`/flags/${flagAsset}.svg`}
              alt={event.region ?? ""}
              width={20}
              height={14}
              style={{ width: "20px", height: "14px", objectFit: "cover" }}
              className="rounded-[1px] ring-1 ring-black/10 dark:ring-white/10 shrink-0 self-center"
              aria-hidden
            />
          ) : (
            <span className="text-base leading-none">{regionFlag(event.region)}</span>
          )}
          <div>
            <div className="text-base font-semibold leading-tight">
              {event.label}
            </div>
            <div className="mt-0.5 flex items-center gap-1.5 text-[14px] text-muted-foreground tracking-wide uppercase">
              <span>{regionLabel(event.region)}</span>
              <span className="opacity-30">·</span>
              <ImportanceDots
                importance={event.importance}
                size="h-1.5 w-1.5"
                gap="gap-0.5"
              />
              <span>
                importanza {IMPORTANCE_LABEL[event.importance].toLowerCase()}
              </span>
            </div>
          </div>
        </div>
      </TooltipContent>
    </Tooltip>
  );
}
