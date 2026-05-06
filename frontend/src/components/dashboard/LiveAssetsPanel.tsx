import {
  Bitcoin,
  CircleDot,
  Globe,
  Loader2,
  type LucideIcon,
} from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { type LiveAsset, useLiveAssets } from "@/hooks/useLiveAssets";
import { cn } from "@/lib/utils";

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

/** Small label above each category group when the list is rendered with
 *  visual separators between sections. */
const CATEGORY_LABEL: Record<LiveAsset["category"], string> = {
  index: "Indici",
  commodity: "Materie prime",
  crypto: "Crypto",
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
  const Icon = CATEGORY_ICON[asset.category];
  const q = asset.quote;
  const price = q?.price ?? null;
  const changePct = q?.change_pct ?? null;
  const isLive = q?.market_state === "OPEN" && q?.error == null;
  const hasError = q == null || q.error != null || q.price == null;

  return (
    <li
      className={cn(
        "flex items-center gap-1.5 px-1.5 py-1 rounded transition-colors",
        "hover:bg-muted/50",
      )}
    >
      {/* Flag (when known) or category icon */}
      <span className="shrink-0 w-[18px] flex items-center justify-center">
        {asset.flag ? (
          <img
            src={`/flags/${asset.flag}.svg`}
            alt={asset.flag}
            width={18}
            height={12}
            style={{ width: "18px", height: "12px", objectFit: "cover" }}
            className="rounded-[2px] ring-1 ring-border/60"
            aria-hidden
          />
        ) : (
          <Icon className="h-3.5 w-3.5 text-muted-foreground/80" />
        )}
      </span>

      {/* Identity: name + live dot */}
      <div className="flex-1 min-w-0 flex items-center gap-1">
        <span className="text-[11.5px] font-semibold truncate leading-tight">
          {asset.name}
        </span>
        {isLive && (
          <span
            className="relative inline-flex h-1.5 w-1.5 shrink-0"
            title="Mercato aperto · prezzo live"
          >
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60" />
            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
          </span>
        )}
      </div>

      {/* Price + change inline (right-aligned, tighter than the old
          two-row layout to fit two columns in the same vertical budget) */}
      <div className="text-right shrink-0 flex items-baseline gap-1.5 leading-tight">
        <span className="text-[11.5px] font-bold tabular-nums">
          {hasError ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="text-muted-foreground/60 cursor-help">—</span>
              </TooltipTrigger>
              <TooltipContent side="left" className="text-[11px]">
                {q?.error ?? "Quotazione non disponibile"}
              </TooltipContent>
            </Tooltip>
          ) : (
            fmtPrice(price)
          )}
        </span>
        <span
          className={cn(
            "text-[10px] font-semibold tabular-nums tracking-tight w-[44px] text-right",
            changeColor(changePct),
          )}
        >
          {fmtPct(changePct)}
        </span>
      </div>
    </li>
  );
}

/** Subtle uppercase divider above each category section. Separated from
 *  the row component because both columns render multiple categories. */
function CategoryHeader({ category }: { category: LiveAsset["category"] }) {
  return (
    <div className="px-1.5 pt-1 pb-0.5 text-[9px] uppercase tracking-[0.16em] text-muted-foreground/60 font-semibold">
      {CATEGORY_LABEL[category]}
    </div>
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
    <Card className="h-full overflow-hidden">
      <CardContent className="p-3 flex flex-col h-full min-h-0">
        <SectionTitle
          icon={Globe}
          label="Mercati live"
          className="mb-2 px-1 shrink-0"
          right={
            q.isFetching ? (
              <Loader2 className="h-3 w-3 animate-spin text-muted-foreground/60" />
            ) : undefined
          }
        />
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
      </CardContent>
    </Card>
  );
}

/** One vertical column rendering ≥1 category sections back-to-back.
 *  The two columns share the SectionTitle above; any number of groups
 *  per column is supported. */
function Column({
  groups,
  className,
}: {
  groups: Array<{ category: LiveAsset["category"]; rows: LiveAsset[] }>;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0", className)}>
      {groups.map((g) => (
        <div key={g.category} className="mb-1 last:mb-0">
          <CategoryHeader category={g.category} />
          <ul className="space-y-0">
            {g.rows.map((asset) => (
              <AssetRow key={asset.symbol} asset={asset} />
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
