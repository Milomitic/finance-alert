import type { IndexBreadth, MarketGlobal } from "@/api/types";
import { LiveAssetsPanel } from "@/components/dashboard/LiveAssetsPanel";
import { MoodCard } from "@/components/dashboard/MoodCard";

interface Props {
  global: MarketGlobal;
  byIndex: IndexBreadth[];
}

/* ─── HeroStrip — top of dashboard ──────────────────────────────────────── *
 *
 * Two columns, side-by-side at 300px row height (lg+):
 *
 *   ┌──── MoodCard (3fr) ────┐  ┌──── LiveAssetsPanel (2fr) ────┐
 *   │ market mood hero        │  │ vertical list of indices,    │
 *   │ (S&P breadth, sentiment │  │ commodities, crypto with     │
 *   │  arc, sector chips)     │  │ live prices + Δ%             │
 *   └─────────────────────────┘  └──────────────────────────────┘
 *
 * Previous iterations had three columns (Mood + GlobalKpiTiles + Scan).
 * Both side panels are gone:
 *   - GlobalKpiTiles → replaced by LiveAssetsPanel (more useful at-a-glance
 *     market context: "what's gold doing today" beats "RSI<30 count")
 *   - ScanTriggerCard → moved to the page header as a small icon button
 *     (the scan flow is admin-on-demand; it doesn't need real estate)
 */
export function HeroStrip({ global, byIndex }: Props) {
  return (
    <div className="grid gap-3 lg:grid-cols-[3fr_2fr] lg:h-[300px]">
      <div className="h-full min-h-0">
        <MoodCard global={global} byIndex={byIndex} />
      </div>
      <div className="h-full min-h-0">
        <LiveAssetsPanel />
      </div>
    </div>
  );
}
