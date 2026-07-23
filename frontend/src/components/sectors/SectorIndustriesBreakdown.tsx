import { Factory } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
  IndustryListItem,
  IndustryRankRow,
} from "@/components/sectors/SectorOverviewTiles";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import type { IndustryRow } from "@/hooks/useSectorDetail";
import { getSectorIcon, getSectorIconColor } from "@/lib/sectorMeta";
import { cn } from "@/lib/utils";

/* The "Sotto-settori" breakdown section of the overview hub, with its own
 * by-sector / flat-ranking view toggle. Owns the view-mode state (the page
 * never reads it back) and the parent-sector grouping memo — extracted so
 * SectorsOverviewPage stays a thin layout orchestrator. */
export function SectorIndustriesBreakdown({ industries }: { industries: IndustryRow[] }) {
  // "by-sector" groups under each sector header, "flat" lists all in one
  // ranked list. Default by-sector because that's the most useful entry
  // point on first land — the user typically wants "what's IN technology?"
  // rather than a global industry leaderboard.
  const [industryView, setIndustryView] = useState<"by-sector" | "flat">(
    "by-sector",
  );

  // Group industries by parent sector for the "by-sector" view.
  const industriesBySector = useMemo(() => {
    const m = new Map<string, IndustryRow[]>();
    for (const ind of industries) {
      const key = ind.sector ?? "(altro)";
      const list = m.get(key) ?? [];
      list.push(ind);
      m.set(key, list);
    }
    return m;
  }, [industries]);

  return (
    <div>
      <SectionTitle
        icon={Factory}
        label={`Sotto-settori (${industries.length})`}
        className="mb-3"
        right={
          <div className="inline-flex rounded-md border bg-card overflow-hidden">
            <button
              type="button"
              onClick={() => setIndustryView("by-sector")}
              className={cn(
                "px-3 py-1 text-xs font-mono uppercase tracking-wider transition-colors",
                industryView === "by-sector"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent",
              )}
            >
              Per settore
            </button>
            <button
              type="button"
              onClick={() => setIndustryView("flat")}
              className={cn(
                "px-3 py-1 text-xs font-mono uppercase tracking-wider transition-colors border-l",
                industryView === "flat"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent",
              )}
            >
              Classifica
            </button>
          </div>
        }
      />

      {industryView === "by-sector" ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
          {Array.from(industriesBySector.entries()).map(([sector, rows]) => {
            const SectorIcon = getSectorIcon(sector);
            const iconColor = getSectorIconColor(sector);
            return (
              <Card key={sector} className="overflow-hidden">
                <CardContent className="p-3">
                  <Link
                    to={`/sectors/${encodeURIComponent(sector)}`}
                    className="flex items-center gap-2 px-2 py-1.5 mb-2 rounded-md hover:bg-muted/60 transition-colors"
                  >
                    <SectorIcon
                      className={cn("h-4 w-4 shrink-0", iconColor)}
                      aria-hidden
                    />
                    <span className="font-semibold text-sm truncate">
                      {sector}
                    </span>
                    <span className="ml-auto text-[11px] text-muted-foreground tabular-nums">
                      {rows.length} industries
                    </span>
                  </Link>
                  <div className="space-y-0.5">
                    {rows.map((ind) => (
                      <IndustryListItem key={ind.name} industry={ind} />
                    ))}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      ) : (
        /* Flat ranking — sorted by avg score desc, then stock count desc */
        <Card>
          <CardContent className="p-3">
            <div className="space-y-0.5">
              {[...industries]
                .sort((a, b) => {
                  const sa = a.avg_score ?? -Infinity;
                  const sb = b.avg_score ?? -Infinity;
                  if (sa !== sb) return sb - sa;
                  return b.stock_count - a.stock_count;
                })
                .map((ind) => (
                  <IndustryRankRow key={`${ind.sector}-${ind.name}`} industry={ind} />
                ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
