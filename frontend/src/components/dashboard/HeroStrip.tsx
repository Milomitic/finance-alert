import type { MarketGlobal } from "@/api/types";
import { DataFreshnessCard } from "@/components/dashboard/DataFreshnessCard";
import { GlobalKpiTiles } from "@/components/dashboard/GlobalKpiTiles";
import { MoodCard } from "@/components/dashboard/MoodCard";

interface Props {
  global: MarketGlobal;
  computedAt: string | null | undefined;
  isStale: boolean;
  nextScanAt: string | null;
}

export function HeroStrip({ global, computedAt, isStale, nextScanAt }: Props) {
  return (
    <div className="grid gap-3 lg:grid-cols-[220px_1fr_220px]">
      <MoodCard global={global} />
      <GlobalKpiTiles global={global} />
      <DataFreshnessCard
        computedAt={computedAt}
        isStale={isStale}
        nextScanAt={nextScanAt}
      />
    </div>
  );
}
