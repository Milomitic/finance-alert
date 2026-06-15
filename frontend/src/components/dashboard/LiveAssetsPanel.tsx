import type * as React from "react";
import {
  Bitcoin,
  CircleDot,
  Coins,
  Droplet,
  Flame,
  Globe,
  Loader2,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router-dom";

import { Sparkline } from "@/components/dashboard/Sparkline";
import { Card, CardContent } from "@/components/ui/card";
import { FlashValue } from "@/components/ui/FlashValue";
import { SectionTitle } from "@/components/ui/section-title";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { type LiveAsset, useLiveAssets } from "@/hooks/useLiveAssets";
import { cn } from "@/lib/utils";

/** Custom Ethereum diamond — lucide-react doesn't ship this brand mark.
 *  Two stacked triangle pairs in the canonical ETH logo proportions.
 *  Uses currentColor so caller controls hue via Tailwind text classes. */
function EthereumIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 256 416"
      className={className}
      fill="currentColor"
      aria-hidden
    >
      <path d="M127.961 0L125.166 9.5v275.668l2.795 2.79 127.962-75.638z" opacity="0.8" />
      <path d="M127.962 0L0 212.32l127.962 75.639V154.158z" />
      <path d="M127.961 312.187l-1.575 1.92v98.199l1.575 4.6L256 236.587z" opacity="0.8" />
      <path d="M127.962 416.905v-104.72L0 236.587z" />
      <path d="M127.961 287.958l127.96-75.637-127.96-58.162z" opacity="0.5" />
      <path d="M0 212.32l127.96 75.638V154.159z" opacity="0.65" />
    </svg>
  );
}

/* ─── LiveAssetsPanel — replaces the old GlobalKpiTiles ────────────────── */
/* A vertical list of curated live snapshots — major equity indices, the
 * commodities a finance-news headline references on a typical morning
 * (gold, silver, oil, gas), and the two largest crypto pairs. Polls
 * `/api/dashboard/live-assets` every 15s; paused when the tab is in
 * the background.
 *
 * Sits to the right of the MoodCard in the dashboard hero. The cards
 * to its right (ScanTriggerCard) used to occupy this slot in earlier
 * iterations — that flow moved to a small action button in the page
 * header so the hero strip can be all market context.
 */

const CATEGORY_ICON: Record<LiveAsset["category"], LucideIcon> = {
  index: Globe,
  commodity: CircleDot,
  crypto: Bitcoin,
};

/** Per-symbol icon override for commodities + crypto. Indices use the
 *  country flag instead, so they don't appear here. Each entry is the
 *  icon component plus a Tailwind text-color class — the icon paints
 *  via `currentColor`, and we want gold to be amber, oil to be slate,
 *  etc. */
type IconRender = {
  Component: React.ComponentType<{ className?: string }>;
  color: string;
};

const SYMBOL_ICON: Record<string, IconRender> = {
  // Commodities — `Coins` for the precious metals, `Droplet` for oil,
  // `Flame` for gas. The colors mirror conventional finance-news
  // chyrons (gold = amber, silver = zinc, oil = dark slate, gas =
  // orange).
  "GC=F": { Component: Coins, color: "text-amber-500" },
  "SI=F": { Component: Coins, color: "text-zinc-400 dark:text-zinc-300" },
  "CL=F": { Component: Droplet, color: "text-slate-700 dark:text-slate-200" },
  "NG=F": { Component: Flame, color: "text-orange-500" },
  // Crypto — Bitcoin from lucide; Ethereum is a custom inline SVG
  // (see top of file) since lucide doesn't ship the brand mark.
  "BTC-USD": { Component: Bitcoin, color: "text-orange-500" },
  "ETH-USD": { Component: EthereumIcon, color: "text-indigo-500 dark:text-indigo-400" },
};

function fmtPrice(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  // Crypto can be < $1 (small cap altcoins); commodities + indices are
  // usually 4-6 digits. Formatter chooses precision per magnitude.
  const abs = Math.abs(v);
  if (abs >= 1000) return v.toLocaleString("it-IT", { maximumFractionDigits: 0 });
  if (abs >= 100) return v.toFixed(2);
  if (abs >= 1) return v.toFixed(2);
  return v.toFixed(4);
}

function fmtPct(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function changeColor(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "text-muted-foreground";
  if (v > 0) return "text-emerald-600 dark:text-emerald-400";
  if (v < 0) return "text-rose-600 dark:text-rose-400";
  return "text-muted-foreground";
}

/* ─── Row ─────────────────────────────────────────────────────────────── */

function AssetRow({ asset }: { asset: LiveAsset }) {
  const FallbackIcon = CATEGORY_ICON[asset.category];
  const symbolIcon = SYMBOL_ICON[asset.symbol];
  const q = asset.quote;
  const price = q?.price ?? null;
  const changePct = q?.change_pct ?? null;
  const hasError = q == null || q.error != null || q.price == null;
  // Real-time dot: the backend decides per category (crypto 24/7, futures
  // on the Globex session, cash during exchange hours) — covers the
  // after-hours futures rows the old "market_state === OPEN" missed.
  const isLive = !!asset.is_live && !hasError;

  // Sparkline trend: based on the change vs. first historical close
  // (so the visual matches the visible series, not just the last
  // intraday tick).
  const history = asset.history ?? [];
  let trend: "up" | "down" | "flat" = "flat";
  if (history.length >= 2) {
    const first = history[0];
    const last = history[history.length - 1];
    if (first > 0) {
      const dp = (last - first) / first;
      trend = dp > 0.001 ? "up" : dp < -0.001 ? "down" : "flat";
    }
  }

  return (
    <li className="flex-1 flex min-h-0">
      <Link
        to={`/markets/${encodeURIComponent(asset.quote_symbol || asset.symbol)}`}
        className={cn(
          "flex-1 flex items-center gap-2 px-1.5 rounded transition-colors min-h-0",
          "hover:bg-muted/50",
        )}
        title={`Apri dettaglio ${asset.name}`}
      >
      {/* Flag (indices) or per-symbol brand icon (commodities/crypto) */}
      <span className="shrink-0 w-[22px] flex items-center justify-center">
        {asset.flag ? (
          <img
            src={`/flags/${asset.flag}.svg`}
            alt={asset.flag}
            width={22}
            height={16}
            style={{ width: "22px", height: "16px", objectFit: "cover" }}
            className="rounded-[2px] ring-1 ring-border/60"
            aria-hidden
          />
        ) : symbolIcon ? (
          <symbolIcon.Component className={cn("h-[18px] w-[18px]", symbolIcon.color)} />
        ) : (
          <FallbackIcon className="h-[18px] w-[18px] text-muted-foreground/80" />
        )}
      </span>

      {/* Identity: name + real-time dot. The pulsing emerald dot fires
          whenever the displayed price updates live — cash session for
          regular-hours indices, the Globex futures session for the
          after-hours index/commodity rows, 24/7 for crypto. (The old
          amber "FUT" badge was dropped: the futures price IS the live
          price after the cash close, so it gets the same live dot.) */}
      <div className="shrink-0 min-w-0 flex items-center gap-1.5">
        <span className="text-[15px] font-semibold truncate leading-tight">
          {asset.name}
        </span>
        {isLive && (
          <span
            className="relative inline-flex h-1.5 w-1.5 shrink-0"
            title={
              asset.using_futures
                ? "Prezzo live dal contratto futures"
                : "Mercato aperto · prezzo live"
            }
          >
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60" />
            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
          </span>
        )}
      </div>

      {/* Sparkline — fills the gap between name and price with the
          recent trend, fading in from left. The SVG itself is
          `width="100%"` so it stretches to whatever flex-grow gives
          it; `min-w-[60px]` is a floor so very narrow viewports still
          show a meaningful trend. Hidden under sm: where the row is
          already busy enough. */}
      <div className="flex-1 min-w-[60px] hidden sm:flex items-center pl-1 pr-2">
        {history.length >= 2 ? (
          <Sparkline data={history} trend={trend} height={22} />
        ) : null}
      </div>

      {/* Price + change inline */}
      <div className="text-right shrink-0 flex items-baseline gap-1.5 leading-tight">
        {hasError ? (
          <span className="text-[15px] font-bold tabular-nums">
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="text-muted-foreground/60 cursor-help">—</span>
              </TooltipTrigger>
              <TooltipContent side="left" className="text-[11px]">
                {q?.error ?? "Quotazione non disponibile"}
              </TooltipContent>
            </Tooltip>
          </span>
        ) : (
          <FlashValue
            value={price}
            format={fmtPrice}
            className="text-[15px] font-bold tabular-nums"
            noTween
            showArrow
          />
        )}
        <span
          className={cn(
            "text-[13px] font-semibold tabular-nums tracking-tight w-[56px] text-right",
            changeColor(changePct),
          )}
        >
          {fmtPct(changePct)}
        </span>
      </div>
      </Link>
    </li>
  );
}


/* ─── Card ────────────────────────────────────────────────────────────── */

export function LiveAssetsPanel() {
  const q = useLiveAssets();
  const assets = q.data?.assets ?? [];

  // Group by category for visual separators. Order is fixed by the
  // server response — we don't re-sort per category.
  const groups: Array<{ category: LiveAsset["category"]; rows: LiveAsset[] }> = [];
  let currentCategory: LiveAsset["category"] | null = null;
  for (const a of assets) {
    if (a.category !== currentCategory) {
      groups.push({ category: a.category, rows: [a] });
      currentCategory = a.category;
    } else {
      groups[groups.length - 1].rows.push(a);
    }
  }

  // Two-column layout: indices on the left (the dominant group, ~7
  // rows), commodities + crypto on the right. Splitting at index 1 is
  // robust to backend reordering as long as the canonical 3 categories
  // remain — if a fourth category lands one day, it'll just append to
  // the right column.
  const leftGroups = groups.slice(0, 1);
  const rightGroups = groups.slice(1);

  return (
    <Card className="h-full overflow-hidden flex flex-col">
      <CardContent className="p-0 flex-1 min-h-0 flex flex-col">
        <div className="shrink-0 px-3 py-2 border-b bg-muted/30">
          <SectionTitle
            icon={Globe}
            label="Mercati live"
            right={
              q.isFetching ? (
                <Loader2 className="h-3 w-3 animate-spin text-muted-foreground/60" />
              ) : undefined
            }
          />
        </div>
        <div className="flex-1 min-h-0 flex flex-col p-3">
        {q.isLoading ? (
          <div className="grid grid-cols-2 gap-x-3 gap-y-1 flex-1 min-h-0 px-1">
            {Array.from({ length: 12 }).map((_, i) => (
              <div
                key={i}
                className="h-7 rounded bg-muted/40 animate-pulse"
              />
            ))}
          </div>
        ) : groups.length === 0 ? (
          <div className="text-xs text-muted-foreground text-center py-6 flex-1">
            Asset non disponibili.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-3 sm:divide-x sm:divide-border/40 flex-1 min-h-0">
            <Column groups={leftGroups} />
            <Column groups={rightGroups} className="sm:pl-3" />
          </div>
        )}
        </div>
      </CardContent>
    </Card>
  );
}

/** One vertical column rendering ≥1 category sections back-to-back.
 *  Each `<ul>` is `flex flex-col flex-1` and each `<li>` inside it is
 *  `flex-1`, so rows distribute the available height evenly within
 *  their group. With multiple groups per column, the groups themselves
 *  flex proportionally to their row counts, which keeps both columns
 *  visually balanced (left has 7 indices, right has 4 commodities + 2
 *  crypto = 6 rows). */
function Column({
  groups,
  className,
}: {
  groups: Array<{ category: LiveAsset["category"]; rows: LiveAsset[] }>;
  className?: string;
}) {
  // Total row count drives the flex-grow weight so groups with more
  // rows take proportionally more vertical space.
  const totalRows = groups.reduce((acc, g) => acc + g.rows.length, 0) || 1;
  return (
    <div className={cn("min-w-0 flex flex-col h-full", className)}>
      {groups.map((g) => (
        <div
          key={g.category}
          className="flex flex-col min-h-0"
          style={{ flexGrow: g.rows.length / totalRows, flexBasis: 0 }}
        >
          {/* Category headers (INDICI / MATERIE PRIME / CRYPTO) removed per
              user request — the rows reclaim that vertical space (taller rows).
              The left column is all indices and the right column is
              commodities + crypto, so the grouping still reads spatially. */}
          <ul className="flex flex-col flex-1 min-h-0">
            {g.rows.map((asset) => (
              <AssetRow key={asset.symbol} asset={asset} />
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
