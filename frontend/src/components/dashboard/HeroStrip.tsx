import type { IndexBreadth, MarketGlobal } from "@/api/types";
import { GlobalKpiTiles } from "@/components/dashboard/GlobalKpiTiles";
import { MoodCard } from "@/components/dashboard/MoodCard";

interface Props {
  global: MarketGlobal;
  byIndex: IndexBreadth[];
}

export function HeroStrip({ global, byIndex }: Props) {
  return (
    <div className="grid gap-3 lg:grid-cols-[3fr_2fr] lg:h-[300px]">
      <div className="h-full min-h-0">
        <MoodCard global={global} byIndex={byIndex} />
      </div>
      <div className="h-full min-h-0">
        <GlobalKpiTiles global={global} />
      </div>
    </div>
  );
}
