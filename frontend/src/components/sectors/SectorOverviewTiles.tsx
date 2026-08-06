import type { IndustryRow } from "@/hooks/useSectorDetail";
import { fmtNum } from "@/lib/sectorFormat";
import { cn } from "@/lib/utils";

/* Industry row components for the sectors overview hub.
 *
 * WHAT USED TO BE HERE. The file was named for `SectorTile` and `SummaryTile`,
 * both now gone: ESP-2 replaced the eleven-card sector grid with
 * SectorLensMatrix + SectorLensTable, and the four universe totals moved onto
 * the page header line in August 2026. Neither component had a caller left.
 * What survives is the two industry rows, which SectorIndustriesBreakdown
 * still renders.
 *
 * `scoreColor` below is LOCAL and uses the hub's softer emerald/rose palette —
 * deliberately distinct from the detail page's bolder green/red map (the two
 * pages never render together). Literal class strings per the Tailwind-purger
 * rule (CLAUDE.md): the purger only sees string literals, so composing these
 * from a template would strip them from the production build, invisibly. */
function scoreColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return "text-muted-foreground";
  if (score >= 70) return "text-emerald-600 dark:text-emerald-400";
  if (score >= 50) return "text-foreground";
  if (score >= 30) return "text-amber-600 dark:text-amber-400";
  return "text-rose-600 dark:text-rose-400";
}

/* ─── Industry row in the breakdown table ─────────────────────────────── */
export function IndustryListItem({ industry }: { industry: IndustryRow }) {
  return (
    <div className="flex items-center gap-3 px-3 py-2 rounded-md hover:bg-muted/50 transition-colors">
      <div className="min-w-0 flex-1">
        <div className="font-medium text-sm truncate" title={industry.name}>
          {industry.name}
        </div>
      </div>
      <div className="text-xs text-muted-foreground tabular-nums shrink-0">
        {industry.stock_count} stock
      </div>
      <div
        className={cn(
          "text-sm font-semibold tabular-nums shrink-0 w-12 text-right",
          scoreColor(industry.avg_score),
        )}
      >
        {fmtNum(industry.avg_score, 0)}
      </div>
    </div>
  );
}

/* Flat ("Classifica") variant — like IndustryListItem but with the parent
 * sector shown as a sub-label, for the cross-sector ranked list. */
export function IndustryRankRow({ industry }: { industry: IndustryRow }) {
  return (
    <div className="flex items-center gap-3 px-3 py-2 rounded-md hover:bg-muted/50 transition-colors">
      <div className="min-w-0 flex-1">
        <div className="font-medium text-sm truncate">{industry.name}</div>
        {industry.sector && (
          <div className="text-xs text-muted-foreground truncate">
            {industry.sector}
          </div>
        )}
      </div>
      <div className="text-xs text-muted-foreground tabular-nums shrink-0">
        {industry.stock_count} stock
      </div>
      <div
        className={cn(
          "text-sm font-semibold tabular-nums shrink-0 w-12 text-right",
          scoreColor(industry.avg_score),
        )}
      >
        {fmtNum(industry.avg_score, 0)}
      </div>
    </div>
  );
}
