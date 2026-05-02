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
    <div className="grid gap-3 lg:grid-cols-[340px_1fr_200px]">
      <MoodCard global={global} byIndex={byIndex} />
      <GlobalKpiTiles global={global} />
      <DataFreshnessCard
        computedAt={computedAt}
        isStale={isStale}
        nextScanAt={nextScanAt}
      />
    </div>
  );
}
