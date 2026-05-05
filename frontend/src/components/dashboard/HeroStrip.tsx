import type { IndexBreadth, MarketGlobal } from "@/api/types";
import { GlobalKpiTiles } from "@/components/dashboard/GlobalKpiTiles";
import { MoodCard } from "@/components/dashboard/MoodCard";
import { ScanTriggerCard } from "@/components/dashboard/ScanTriggerCard";

interface Props {
  global: MarketGlobal;
  byIndex: IndexBreadth[];
  /** Forwarded to ScanTriggerCard for the "next scheduled scan" footer. */
  nextScanAt?: string | null;
}

/* ─── HeroStrip — top of dashboard ──────────────────────────────────────── */
/* Mood card on the LEFT (3fr) — the editorial, eye-catching hero.
 * Sidebar on the RIGHT (1.6fr): two stacked cards forming a slim control
 * rail — Global KPI list + Scan trigger. Used to be a 2fr column with the
 * KPI tiles in a 2×3 grid; the rework compresses that into a vertical
 * list and reclaims room for the scan controls. */
export function HeroStrip({ global, byIndex, nextScanAt }: Props) {
  return (
    <div className="grid gap-3 lg:grid-cols-[3fr_1.6fr] lg:h-[300px]">
      <div className="h-full min-h-0">
        <MoodCard global={global} byIndex={byIndex} />
      </div>
      <div className="grid gap-3 grid-rows-[1fr_auto] h-full min-h-0">
        <div className="min-h-0">
          <GlobalKpiTiles global={global} />
        </div>
        <ScanTriggerCard nextScanAt={nextScanAt} />
      </div>
    </div>
  );
}
