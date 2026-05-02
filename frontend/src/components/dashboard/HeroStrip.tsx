import type { IndexBreadth, MarketGlobal } from "@/api/types";
import { DataFreshnessCard } from "@/components/dashboard/DataFreshnessCard";
import { GlobalKpiTiles } from "@/components/dashboard/GlobalKpiTiles";
import { MoodCard } from "@/components/dashboard/MoodCard";

interface Props {
  global: MarketGlobal;
  byIndex: IndexBreadth[];
  computedAt: string | null | undefined;
  isStale: boolean;
  nextScanAt: string | null;
}

export function HeroStrip({ global, byIndex, computedAt, isStale, nextScanAt }: Props) {
  return (
    <div className="grid gap-3 lg:grid-cols-[3fr_2fr] lg:h-[320px]">
      <div className="h-full min-h-0">
        <MoodCard global={global} byIndex={byIndex} />
      </div>
      <div className="grid grid-rows-[1fr_auto] gap-3 h-full min-h-0">
        <div className="min-h-0">
          <GlobalKpiTiles global={global} />
        </div>
        <DataFreshnessCard
          computedAt={computedAt}
          isStale={isStale}
          nextScanAt={nextScanAt}
        />
      </div>
    </div>
  );
}
