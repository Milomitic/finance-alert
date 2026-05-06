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
        "flex items-center gap-2 px-2 py-1.5 -mx-1 rounded transition-colors",
        "hover:bg-muted/40",
      )}
    >
      {/* Flag (when known) or category icon */}
      <span className="shrink-0 w-5 flex items-center justify-center">
        {asset.flag ? (
          <img
            src={`/flags/${asset.flag}.svg`}
            alt={asset.flag}
            width={18}
            height={12}
            style={{ width: "18px", height: "12px", objectFit: "cover" }}
            className="rounded-[2px] shadow-sm"
            aria-hidden
          />
        ) : (
          <Icon className="h-3.5 w-3.5 text-muted-foreground" />
        )}
      </span>

      {/* Identity: symbol + name */}
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-1.5">
          <span className="text-[12.5px] font-bold tabular-nums truncate">
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
        <div className="text-[10px] text-muted-foreground/70 tabular-nums truncate">
          {asset.symbol}
        </div>
      </div>

      {/* Price + change */}
      <div className="text-right shrink-0">
        <div className="text-[13px] font-bold tabular-nums leading-tight">
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
        </div>
        <div
          className={cn(
            "text-[10.5px] font-semibold tabular-nums leading-tight",
            changeColor(changePct),
          )}
        >
          {fmtPct(changePct)}
        </div>
      </div>
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
        <div className="flex-1 min-h-0 overflow-y-auto">
          {q.isLoading ? (
            <div className="space-y-2 p-2">
              {Array.from({ length: 8 }).map((_, i) => (
                <div
                  key={i}
                  className="h-8 rounded bg-muted/40 animate-pulse"
                />
              ))}
            </div>
          ) : groups.length === 0 ? (
            <div className="text-xs text-muted-foreground text-center py-6">
              Asset non disponibili.
            </div>
          ) : (
            <ul className="space-y-0">
              {groups.map((g, gi) => (
                <li key={g.category}>
                  {/* Category divider — subtle uppercase label between
                      sections (Indici / Materie prime / Crypto) */}
                  {gi > 0 && (
                    <div className="my-1 mx-2 border-t border-border/40" />
                  )}
                  <div className="px-2 pt-1 pb-0.5 text-[9.5px] uppercase tracking-[0.14em] text-muted-foreground/60 font-semibold">
                    {CATEGORY_LABEL[g.category]}
                  </div>
                  <ul>
                    {g.rows.map((asset) => (
                      <AssetRow key={asset.symbol} asset={asset} />
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
