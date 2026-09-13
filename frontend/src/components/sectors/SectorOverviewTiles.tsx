import type { IndustryRow } from "@/hooks/useSectorDetail";
import { fmtNum } from "@/lib/format";
import { cn } from "@/lib/utils";
import { avgScoreColor } from "@/lib/sectorScoreColor";

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
          avgScoreColor(industry.avg_score),
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
          avgScoreColor(industry.avg_score),
        )}
      >
        {fmtNum(industry.avg_score, 0)}
      </div>
    </div>
  );
}
